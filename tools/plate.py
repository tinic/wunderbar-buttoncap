#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Lay out built caps on one plate as a Bambu Studio project 3MF.

usage: plate.py SPEC.json OUT.3mf

SPEC.json:
  {
    "bed": [330, 320],                      # printable area, mm
    "filaments": {"Red": 1, "White": 2},    # colour name -> filament slot in the printer
    "letter_filaments": {"White": 2},       # optional: other slots for the letters, such as
                                            # spools on a finer nozzle
    "rows": [                               # one list of caps per row, front row last
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

Each cap is an object with two parts, Cap and Label, each set to the filament of its
colour (from labels/<type>.csv). The file carries no printer or process settings, so
Bambu Studio keeps the ones it has. Build the caps first (make).
"""
import csv, json, os, sys, zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import CAP_TYPES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"


def q(tag):
    return "{%s}%s" % (NS, tag)


def load_parts(path):
    """{"Cap": (verts, tris), "Label": (verts, tris)} from a built cap 3MF."""
    with zipfile.ZipFile(path) as z:
        model = ET.fromstring(z.read("3D/3dmodel.model"))
    parts = {}
    for obj in model.find(q("resources")).findall(q("object")):
        mesh = obj.find(q("mesh"))
        if mesh is None:
            continue
        verts = [(float(v.get("x")), float(v.get("y")), float(v.get("z"))) for v in mesh.find(q("vertices"))]
        tris = [(int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))) for t in mesh.find(q("triangles"))]
        parts[obj.get("name")] = (verts, tris)
    return parts


def main():
    spec_path, out = sys.argv[1], sys.argv[2]
    spec = json.load(open(spec_path))
    bed_w, bed_d = spec["bed"]
    slots = spec["filaments"]
    letter_slots = dict(slots, **spec.get("letter_filaments", {}))
    gap = spec.get("row_gap", 6)
    cmap = spec.get("colour_map", {})
    dark = set(spec.get("dark_colours", ["Red", "Green", "Blue", "Black"]))

    def colours(cap, letter):
        cap, letter = cmap.get(cap, cap), cmap.get(letter, letter)
        if letter == cap or (cap in dark and letter in dark):
            letter = "Black" if cap == "White" else "White"
        return cap, letter

    # Expand "all" rows.
    rows = []
    for row in spec["rows"]:
        if row["caps"] != "all":
            rows.append(row)
            continue
        t = row["type"]
        files = [r["file"] for r in csv.DictReader(open(os.path.join(
            ROOT, "labels", CAP_TYPES[t].get("labels", t) + ".csv")))]
        n = row["per_row"]
        for i in range(0, len(files), n):
            rows.append(dict(row, caps=files[i:i + n]))

    # Load every cap and its colours.
    placed = []
    for row in rows:
        t = row["type"]
        labels = {r["file"]: r for r in csv.DictReader(open(os.path.join(
            ROOT, "labels", CAP_TYPES[t].get("labels", t) + ".csv")))}
        items = []
        for f in row["caps"]:
            cap_c, let_c = colours(labels[f]["cap"], labels[f]["letter"])
            if cap_c not in slots:
                sys.exit("%s/%s: no filament slot for the %s cap" % (t, f, cap_c))
            if let_c not in letter_slots:
                sys.exit("%s/%s: no filament slot for %s letters" % (t, f, let_c))
            parts = load_parts(os.path.join(ROOT, "build", t, "3mf", f + ".3mf"))
            xs = [v[0] for v in parts["Cap"][0]]
            ys = [v[1] for v in parts["Cap"][0]]
            items.append(dict(type=t, file=f, parts=parts, cap=slots[cap_c], letter=letter_slots[let_c], colours=(cap_c, let_c),
                              w=max(xs) - min(xs), d=max(ys) - min(ys)))
        placed.append((row, items))

    # Grid, centred on the bed. Rows run along X; the first row is at the back (+Y).
    depths = [max(i["d"] for i in items) for _, items in placed]
    total_d = sum(depths) + gap * (len(placed) - 1)
    y = bed_d / 2 + total_d / 2
    for (row, items), depth in zip(placed, depths):
        y -= depth / 2
        n = len(items)
        x0 = bed_w / 2 - row["pitch"] * (n - 1) / 2
        for k, it in enumerate(items):
            it["pos"] = (x0 + k * row["pitch"], y)
        y -= depth / 2 + gap

    # 3MF: one mesh object per part, one parent object per cap with two components.
    res, build_items, cfg = [], [], []
    oid = 1
    for _, items in placed:
        for it in items:
            part_ids = {}
            for name in ("Cap", "Label"):
                verts, tris = it["parts"][name]
                part_ids[name] = oid
                res.append('<object id="%d" type="model"><mesh><vertices>' % oid)
                res.extend('<vertex x="%.5f" y="%.5f" z="%.5f"/>' % v for v in verts)
                res.append("</vertices><triangles>")
                res.extend('<triangle v1="%d" v2="%d" v3="%d"/>' % t for t in tris)
                res.append("</triangles></mesh></object>")
                oid += 1
            parent = oid
            oid += 1
            it["id"] = parent
            res.append('<object id="%d" type="model"><components>'
                       '<component objectid="%d" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
                       '<component objectid="%d" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
                       '</components></object>' % (parent, part_ids["Cap"], part_ids["Label"]))
            build_items.append('<item objectid="%d" transform="1 0 0 0 1 0 0 0 1 %.4f %.4f 0" printable="1"/>'
                               % (parent, it["pos"][0], it["pos"][1]))
            name = "%s %s" % (it["type"], it["file"])
            cfg.append('  <object id="%d">\n    <metadata key="name" value="%s"/>\n'
                       '    <metadata key="extruder" value="%d"/>\n' % (parent, escape(name), it["cap"]))
            for pname, pid, ext in (("Cap", part_ids["Cap"], it["cap"]), ("Label", part_ids["Label"], it["letter"])):
                cfg.append('    <part id="%d" subtype="normal_part">\n      <metadata key="name" value="%s"/>\n'
                           '      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
                           '      <metadata key="extruder" value="%d"/>\n    </part>\n' % (pid, pname, ext))
            cfg.append("  </object>\n")
    cfg.append('  <plate>\n    <metadata key="plater_id" value="1"/>\n    <metadata key="plater_name" value=""/>\n'
               '    <metadata key="locked" value="false"/>\n')
    for k, (_, items) in enumerate(placed):
        pass
    inst = 0
    for _, items in placed:
        for it in items:
            cfg.append('    <model_instance>\n      <metadata key="object_id" value="%d"/>\n'
                       '      <metadata key="instance_id" value="0"/>\n'
                       '      <metadata key="identify_id" value="%d"/>\n    </model_instance>\n'
                       % (it["id"], 1000 + inst))
            inst += 1
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
    n = sum(len(items) for _, items in placed)
    from collections import Counter
    used = Counter("%s/%s" % it["colours"] for _, items in placed for it in items)
    print("plate=%s caps=%d rows=%d depth_mm=%.1f" % (out, n, len(placed), total_d))
    print("colours " + " ".join("%s=%d" % kv for kv in sorted(used.items())))


if __name__ == "__main__":
    main()
