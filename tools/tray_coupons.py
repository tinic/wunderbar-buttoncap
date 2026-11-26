#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fit-test coupons of the storage tray in several collar sizes, on one plate.

usage: tray_coupons.py [--out build/tray/CapTray-fit-coupons.3mf]

Each coupon is a corner of the tray (cad/tray/coupon.json) built with one pair of
collar sizes (round collar_d / long lcollar_w), which it carries engraved on its
underside. Print the plate, try caps on every coupon, and set the sizes that hold
best in cad/tray/CapTray.sc.
"""
import argparse, os, subprocess, sys, tempfile, zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
# (round collar_d, long lcollar_w) in mm: the cap's rib is 7.2 mm, the long cap's ridge 4.506 mm.
SIZES = [(7.30, 4.60), (7.35, 4.65), (7.40, 4.70), (7.45, 4.75),
         (7.50, 4.80), (7.55, 4.85), (7.60, 4.90), (7.65, 4.95)]
COLS, DX, DY = 4, 50.0, 45.0   # plate grid: columns and pitch, mm


def build(size, tmp):
    d, w = size
    out = os.path.join(tmp, "coupon-%.2f-%.2f.3mf" % size)
    r = subprocess.run(["solidcraft-cli", "run", os.path.join(ROOT, "cad", "tray", "coupon.json"),
                        "--in", os.path.join(ROOT, "cad", "tray", "CapTray.sc"),
                        "--param", "collar_d=%.2f mm" % d, "--param", "lcollar_w=%.2f mm" % w,
                        "--out", out, "--quiet"], stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("coupon %.2f/%.2f: %s" % (d, w, (r.stderr or r.stdout).strip()[-400:]))
    return out


def mesh(path):
    model = ET.fromstring(zipfile.ZipFile(path).read("3D/3dmodel.model"))
    obj = [o for o in model.iter("{%s}object" % NS) if o.find("{%s}mesh" % NS) is not None][0]
    m = obj.find("{%s}mesh" % NS)
    v = [(float(x.get("x")), float(x.get("y")), float(x.get("z"))) for x in m.find("{%s}vertices" % NS)]
    t = [(t.get("v1"), t.get("v2"), t.get("v3")) for t in m.find("{%s}triangles" % NS)]
    return v, t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "tray", "CapTray-fit-coupons.3mf"))
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        with ThreadPoolExecutor(len(SIZES)) as ex:
            files = list(ex.map(lambda s: build(s, tmp), SIZES))
        meshes = [mesh(f) for f in files]
    res, items = [], []
    for k, ((v, t), size) in enumerate(zip(meshes, SIZES)):
        xs, ys = [p[0] for p in v], [p[1] for p in v]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        ox, oy = (k % COLS - (COLS - 1) / 2) * DX - cx, ((len(SIZES) // COLS - 1) / 2 - k // COLS) * DY - cy
        res.append('<object id="%d" type="model" name="coupon %.2f / %.2f"><mesh><vertices>' % ((k + 1,) + size))
        res.extend('<vertex x="%.4f" y="%.4f" z="%.4f"/>' % (p[0] + ox, p[1] + oy, p[2]) for p in v)
        res.append("</vertices><triangles>")
        res.extend('<triangle v1="%s" v2="%s" v3="%s"/>' % tr for tr in t)
        res.append("</triangles></mesh></object>")
        items.append('<item objectid="%d"/>' % (k + 1))
    model = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<model unit="millimeter" xml:lang="en-US" xmlns="%s">' % NS,
             '<metadata name="Title">CapTray fit coupons</metadata>', "<resources>"] + res + \
            ["</resources>", "<build>"] + items + ["</build>", "</model>"]
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
                   '</Relationships>')
        z.writestr("3D/3dmodel.model", "\n".join(model))
    print("coupons=%s sizes=%s" % (a.out, " ".join("%.2f/%.2f" % s for s in SIZES)))


if __name__ == "__main__":
    main()
