#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Lay out built caps on a plate as a Bambu Studio project 3MF.

usage: plate.py SPEC.json OUT.3mf

SPEC.json:
  {
    "bed": [330, 320],                      # printable area, mm
    "filaments": {"Red": 1, "White": 2},    # colour name -> filament slot in the printer
    "letter_filaments": {"White": 8},       # optional: other slots for the letters, such as
                                            # spools on a finer nozzle
    "rows": [                               # rows from the back of the plate to the front
      {"type": "round", "pitch": 15, "caps": ["COKE", "SPRITE"]},
      {"type": "long", "pitch": 26, "caps": ["VODKA"]}
    ],
    "row_gap": 6
  }

A row can also be {"type": "round", "pitch": 13, "per_row": 20, "caps": "all"}: every
cap of that type, in labels CSV order, over as many rows as it takes.

"colour_map": {"Yellow": "White", ...} replaces colours that are not loaded; when that
leaves dark letters on a dark cap (or the same colour), the letters become White, or
Black on a white cap.

"letters": ["Black", "Blue"] keeps only the caps with those letter colours (after
"colour_map").

"split_by": "letter" writes one project per letter colour: OUT-<colour>-letters.3mf.

"project_settings": "plates/bambu/h3c-multi-diameter.json" embeds a Bambu Studio
project_settings.config (printer, process, filaments, nozzle map; see docs/bambu-3mf.md),
so the project opens with those settings. Its filament list must match "filaments".
Without it, Bambu Studio loads the geometry only and keeps its current settings.

"max_triangles": {"round": [5000, 3000], "long": [8000, 3000]} simplifies each Cap and
Label mesh to at most that many triangles (the default). A part whose volume would change
by more than 0.5% keeps its full mesh. SolidCraft's meshes have about 40 000 triangles per
cap, which makes a full plate too slow to work with in Bambu Studio.

Each cap is an object with two parts, Cap and Label, each set to the filament of its
colour (from labels/<type>.csv). The file carries no printer or process settings, so
Bambu Studio keeps the ones it has. Build the caps first (make).
"""
import csv, json, os, sys, zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from xml.sax.saxutils import escape

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import CAP_TYPES
from threemf import simplify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
MAX_TRIANGLES = {"round": [5000, 3000], "long": [8000, 3000]}


def q(tag):
    return "{%s}%s" % (NS, tag)


def load_parts(path, targets):
    """{"Cap": (verts, tris), "Label": (verts, tris)} from a built cap 3MF, simplified."""
    with zipfile.ZipFile(path) as z:
        model = ET.fromstring(z.read("3D/3dmodel.model"))
    parts = {}
    for obj in model.find(q("resources")).findall(q("object")):
        mesh = obj.find(q("mesh"))
        if mesh is None:
            continue
        v = np.array([[float(x.get("x")), float(x.get("y")), float(x.get("z"))] for x in mesh.find(q("vertices"))])
        f = np.array([[int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))] for t in mesh.find(q("triangles"))],
                     dtype=np.int64)
        name = obj.get("name")
        parts[name] = simplify(v, f, targets[0] if name == "Cap" else targets[1])
    return parts


def write(placed, out, bed, gap, settings=None):
    """Centre the rows on the bed (first row at the back) and write the project 3MF."""
    bed_w, bed_d = bed
    depths = [max(i["d"] for i in items) for _, items in placed]
    total_d = sum(depths) + gap * (len(placed) - 1)
    y = bed_d / 2 + total_d / 2
    for (row, items), depth in zip(placed, depths):
        y -= depth / 2
        x0 = bed_w / 2 - row["pitch"] * (len(items) - 1) / 2
        for k, it in enumerate(items):
            it["pos"] = (x0 + k * row["pitch"], y)
        y -= depth / 2 + gap

    res, build_items, cfg, inst = [], [], [], []
    oid = 1
    for _, items in placed:
        for it in items:
            part_ids = {}
            for name in ("Cap", "Label"):
                v, f = it["parts"][name]
                part_ids[name] = oid
                res.append('<object id="%d" type="model"><mesh><vertices>' % oid)
                res.extend('<vertex x="%.4f" y="%.4f" z="%.4f"/>' % tuple(p) for p in v)
                res.append("</vertices><triangles>")
                res.extend('<triangle v1="%d" v2="%d" v3="%d"/>' % tuple(t) for t in f)
                res.append("</triangles></mesh></object>")
                oid += 1
            parent = oid
            oid += 1
            res.append('<object id="%d" type="model"><components>'
                       '<component objectid="%d" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
                       '<component objectid="%d" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
                       '</components></object>' % (parent, part_ids["Cap"], part_ids["Label"]))
            build_items.append('<item objectid="%d" transform="1 0 0 0 1 0 0 0 1 %.4f %.4f 0" printable="1"/>'
                               % (parent, it["pos"][0], it["pos"][1]))
            cfg.append('  <object id="%d">\n    <metadata key="name" value="%s"/>\n'
                       '    <metadata key="extruder" value="%d"/>\n'
                       % (parent, escape("%s %s" % (it["type"], it["file"])), it["cap"]))
            for pname, ext in (("Cap", it["cap"]), ("Label", it["letter"])):
                cfg.append('    <part id="%d" subtype="normal_part">\n      <metadata key="name" value="%s"/>\n'
                           '      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
                           '      <metadata key="extruder" value="%d"/>\n    </part>\n'
                           % (part_ids[pname], pname, ext))
            cfg.append("  </object>\n")
            inst.append(parent)
    cfg.append('  <plate>\n    <metadata key="plater_id" value="1"/>\n    <metadata key="plater_name" value=""/>\n'
               '    <metadata key="locked" value="false"/>\n')
    for k, parent in enumerate(inst):
        cfg.append('    <model_instance>\n      <metadata key="object_id" value="%d"/>\n'
                   '      <metadata key="instance_id" value="0"/>\n'
                   '      <metadata key="identify_id" value="%d"/>\n    </model_instance>\n' % (parent, 1000 + k))
    cfg.append("  </plate>\n")

    model = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<model unit="millimeter" xml:lang="en-US" xmlns="%s" '
             'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021">' % NS,
             '<metadata name="Application">BambuStudio-02.09.01.70</metadata>',
             '<metadata name="BambuStudio:3mfVersion">1</metadata>',
             '<metadata name="Title">wunderbar-buttoncap plate</metadata>',
             "<resources>"] + res + ["</resources>", "<build>"] + build_items + ["</build>", "</model>"]
    config = '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + "".join(cfg) + "</config>\n"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
                   '<Default Extension="png" ContentType="image/png"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
                   '</Relationships>')
        z.writestr("3D/3dmodel.model", "\n".join(model))
        z.writestr("Metadata/model_settings.config", config)
        if settings:
            z.writestr("Metadata/project_settings.config", settings)
    caps = [it for _, items in placed for it in items]
    tris = sum(len(it["parts"][p][1]) for it in caps for p in ("Cap", "Label"))
    used = Counter("%s/%s" % it["colours"] for it in caps)
    print("plate=%s caps=%d rows=%d depth_mm=%.1f triangles=%d bytes=%d colours=%s" % (
        out, len(caps), len(placed), total_d, tris, os.path.getsize(out),
        ",".join("%s:%d" % kv for kv in sorted(used.items()))))


def main():
    spec_path, out = sys.argv[1], sys.argv[2]
    spec = json.load(open(spec_path))
    slots = spec["filaments"]
    letter_slots = dict(slots, **spec.get("letter_filaments", {}))
    gap = spec.get("row_gap", 6)
    cmap = spec.get("colour_map", {})
    dark = set(spec.get("dark_colours", ["Red", "Green", "Blue", "Black"]))
    max_tris = spec.get("max_triangles", MAX_TRIANGLES)
    settings = None
    if spec.get("project_settings"):
        settings = open(os.path.join(ROOT, spec["project_settings"])).read()
        colours_n = len(json.loads(settings).get("filament_colour", []))
        if colours_n < max(list(slots.values()) + list(letter_slots.values())):
            sys.exit("%s has %d filaments; the spec uses slot %d" % (
                spec["project_settings"], colours_n, max(list(slots.values()) + list(letter_slots.values()))))

    def colours(cap, letter):
        cap, letter = cmap.get(cap, cap), cmap.get(letter, letter)
        if letter == cap or (cap in dark and letter in dark):
            letter = "Black" if cap == "White" else "White"
        return cap, letter

    # Load every cap of every row definition.
    defs = []
    for row in spec["rows"]:
        t = row["type"]
        labels = {r["file"]: r for r in csv.DictReader(open(os.path.join(
            ROOT, "labels", CAP_TYPES[t].get("labels", t) + ".csv")))}
        files = list(labels) if row["caps"] == "all" else row["caps"]
        items = []
        for f in files:
            cap_c, let_c = colours(labels[f]["cap"], labels[f]["letter"])
            if cap_c not in slots:
                sys.exit("%s/%s: no filament slot for the %s cap" % (t, f, cap_c))
            if let_c not in letter_slots:
                sys.exit("%s/%s: no filament slot for %s letters" % (t, f, let_c))
            parts = load_parts(os.path.join(ROOT, "build", t, "3mf", f + ".3mf"), max_tris.get(t, [None, None]))
            xs, ys = parts["Cap"][0][:, 0], parts["Cap"][0][:, 1]
            items.append(dict(type=t, file=f, parts=parts, cap=slots[cap_c], letter=letter_slots[let_c],
                              colours=(cap_c, let_c), w=xs.max() - xs.min(), d=ys.max() - ys.min()))
        defs.append((row, items))

    def rows_of(select):
        placed = []
        for row, items in defs:
            chosen = [it for it in items if select(it)]
            n = row.get("per_row", len(chosen)) or 1
            placed += [(row, chosen[i:i + n]) for i in range(0, len(chosen), n)]
        return placed

    keep = set(spec.get("letters", []))
    if keep:
        defs[:] = [(row, [it for it in items if it["colours"][1] in keep]) for row, items in defs]
    if spec.get("split_by") == "letter":
        base = out[:-4] if out.endswith(".3mf") else out
        groups = list(dict.fromkeys(it["colours"][1] for _, items in defs for it in items))
        for g in groups:
            write(rows_of(lambda it: it["colours"][1] == g), "%s-%s-letters.3mf" % (base, g.lower()),
                  spec["bed"], gap, settings)
    else:
        write(rows_of(lambda it: True), out, spec["bed"], gap, settings)


if __name__ == "__main__":
    main()
