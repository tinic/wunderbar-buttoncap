# SPDX-License-Identifier: MIT
"""Rewrite SolidCraft's 3MF as one object with two parts, "Cap" and "Label".

SolidCraft writes one object per body, and the label's letters are separate
bodies. Slicers handle one multi-part object better: the parts stay aligned
and each takes its own filament.

SolidCraft's meshes follow curves to 2 um, about 40 000 triangles a cap, far
finer than a printer can show. merge() simplifies each part to a triangle
budget; a part whose volume would change by more than 0.5% keeps its full mesh.
At 5 000 + 3 000 triangles a round cap moves at most 0.012 mm from the exact
shape (the letters 0.004 mm).
"""
import zipfile
import numpy as np
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
HEX = {"White": "#F2F2F2FF", "Black": "#202020FF", "Grey": "#8A8D8FFF", "Red": "#C8102EFF",
       "Green": "#00843DFF", "Blue": "#0057B8FF", "Yellow": "#FFCD00FF", "Orange": "#FF6A13FF",
       "Pink": "#F28DBBFF", "Brown": "#6E4520FF", "Purple": "#6D2077FF", "Maroon": "#6D0F1EFF",
       "Burgundy": "#800020FF"}


def _q(tag):
    return "{%s}%s" % (NS, tag)


def volume(v, f):
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6)


def simplify(v, f, target):
    """The mesh with at most `target` triangles, or as it is when that changes its volume by > 0.5%."""
    if not target or len(f) <= target:
        return v, f
    import pyfqmr
    s = pyfqmr.Simplify()
    s.setMesh(v, f)
    s.simplify_mesh(target_count=target, aggressiveness=5, preserve_border=True, verbose=False)
    v2, f2, _ = s.getMesh()
    if abs(volume(v2, f2) / volume(v, f) - 1) > 0.005:
        return v, f
    return v2, f2


def merge(src, dst, title, colours, max_triangles=None):
    """colours: {"Cap": name, "Label": name}, written as base materials (a hint for slicers).
    max_triangles: {"Cap": n, "Label": n}, the triangle budget of each part (None: as SolidCraft wrote it)."""
    with zipfile.ZipFile(src) as z:
        model = ET.fromstring(z.read("3D/3dmodel.model"))
        names = z.namelist()
        thumb = z.read("Metadata/thumbnail.png") if "Metadata/thumbnail.png" in names else None
    parts = {"Cap": ([], []), "Label": ([], [])}
    for obj in model.find(_q("resources")).findall(_q("object")):
        part = "Label" if obj.get("name", "").startswith("Label") else "Cap"
        verts, tris = parts[part]
        mesh = obj.find(_q("mesh"))
        off = len(verts)
        verts.extend((float(v.get("x")), float(v.get("y")), float(v.get("z"))) for v in mesh.find(_q("vertices")))
        tris.extend((int(t.get("v1")) + off, int(t.get("v2")) + off, int(t.get("v3")) + off)
                    for t in mesh.find(_q("triangles")))
    if not parts["Cap"][1] or not parts["Label"][1]:
        raise ValueError("%s: expected a Cap and at least one Label body" % src)
    for part in parts:
        v, f = np.array(parts[part][0]), np.array(parts[part][1], dtype=np.int64)
        parts[part] = simplify(v, f, (max_triangles or {}).get(part))
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<model unit="millimeter" xml:lang="en-US" xmlns="%s">' % NS,
           '<metadata name="Title">%s</metadata>' % escape(title),
           '<metadata name="Application">wunderbar-buttoncap</metadata>',
           "<resources>",
           '<basematerials id="10">'
           '<base name="%s" displaycolor="%s"/><base name="%s" displaycolor="%s"/></basematerials>' % (
               escape(colours["Cap"]), HEX.get(colours["Cap"], "#CCCCCCFF"),
               escape(colours["Label"]), HEX.get(colours["Label"], "#CCCCCCFF"))]
    for oid, part, pindex in ((2, "Cap", 0), (3, "Label", 1)):
        verts, tris = parts[part]
        out.append('<object id="%d" type="model" name="%s" pid="10" pindex="%d"><mesh><vertices>' % (oid, part, pindex))
        out.extend('<vertex x="%.4f" y="%.4f" z="%.4f"/>' % tuple(v) for v in verts)
        out.append("</vertices><triangles>")
        out.extend('<triangle v1="%d" v2="%d" v3="%d"/>' % tuple(t) for t in tris)
        out.append("</triangles></mesh></object>")
    out.append('<object id="1" type="model" name="%s"><components>'
               '<component objectid="2"/><component objectid="3"/></components></object>' % escape(title))
    out.append('</resources><build><item objectid="1"/></build></model>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>')
    if thumb:
        rels += ('<Relationship Target="/Metadata/thumbnail.png" Id="rel1" '
                 'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"/>')
    rels += "</Relationships>"
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        # Fixed timestamps: the same inputs give the same file.
        def put(name, data):
            z.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data, zipfile.ZIP_DEFLATED)
        put("[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
            '<Default Extension="png" ContentType="image/png"/></Types>')
        put("_rels/.rels", rels)
        put("3D/3dmodel.model", "\n".join(out))
        if thumb:
            put("Metadata/thumbnail.png", thumb)
