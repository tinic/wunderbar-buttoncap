#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build WunderBar bar gun button caps: one 3MF and one preview PNG per label.

usage: build.py [--type round] [--only FILE,...] [--jobs N] [--force]

Reads labels/<type>.csv (file,label,cap,letter,source) and cad/<type>/GunCap.sc.
Writes build/<type>/3mf/<FILE>.3mf and build/<type>/preview/<FILE>.png, and skips
a cap whose inputs (design, font, label, colours, this script) have not changed.
Each label is fitted to the cap face: one line, or two lines at a space when that
gives bigger letters; "|" in a label forces the line break.

Each 3MF holds one object with two parts, "Cap" and "Label": in the slicer, give
each part its filament.
"""
import argparse, csv, hashlib, json, os, subprocess, sys, tempfile, zipfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import textfit
import threemf
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")

# One entry per cap type. "labels" names the labels CSV when it is not <type>.csv.
CAP_TYPES = {
    "round": dict(
        design="cad/round/GunCap.sc",
        sketch="LabelSketch",
        text_link="j1",
        font="fonts/Anton-Regular.ttf",
        fit_r=4.5,          # each line's box corners stay inside this radius (face flat is R4.6)
        h_max=7.0,          # largest capital height
        line_spacing=0.62,  # times the font's line distance
        two_line_gain=1.12, # two lines only when the letters get this much bigger
        camera={"target": [0, 0, 1.6], "yaw": 3.14159, "pitch": -0.95, "distance": 26},
    ),
    # Wunder-Bar long button cap, 20.32 x 8.26 mm.
    "long": dict(
        design="cad/long/LongCap.sc",
        sketch="LabelSketch",
        text_link="j1",
        font="fonts/Anton-Regular.ttf",
        # The flat face is about 19.8 x 5.76 mm with round ends. Each line's box corners
        # stay 0.4 mm inside it: a stadium of two R2.48 ends 14.06 mm apart.
        fit_stadium=[7.03, 2.48],
        h_max=4.2,
        line_spacing=0.62,
        two_line_gain=1.12,
        camera={"target": [0, 0, 2.0], "yaw": 3.14159, "pitch": -1.1, "distance": 36},
    ),
}

COLOURS = {
    "White": "#f2f2f2", "Black": "#202020", "Grey": "#8a8d8f", "Red": "#c8102e",
    "Green": "#00843d", "Blue": "#0057b8", "Yellow": "#ffcd00", "Orange": "#ff6a13",
    "Pink": "#f28dbb", "Brown": "#6e4520", "Purple": "#6d2077", "Maroon": "#6d0f1e",
    "Burgundy": "#800020",
}


def line_factor(font):
    f = TTFont(font)
    hh = f["hhea"]
    return (hh.ascent - hh.descent + hh.lineGap) / f["OS/2"].sCapHeight


def corner_scale(x, y, cfg):
    """Largest s that keeps the point (s*x, s*y) inside the face's fit shape."""
    if "fit_stadium" not in cfg:
        return cfg["fit_r"] / max(1e-9, (x * x + y * y) ** 0.5)
    a, r = cfg["fit_stadium"]

    def inside(s):
        px, py = abs(s * x), abs(s * y)
        dx = max(0.0, px - a)
        return dx * dx + py * py <= r * r

    lo, hi = 0.0, 1000.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if inside(mid) else (lo, mid)
    return lo


def fit(lines, font, cfg):
    """Capital height that keeps every line's box inside the face's fit shape."""
    ld = line_factor(font) * cfg["line_spacing"]
    top = (1 + (len(lines) - 1) * ld) / 2  # first line's capital top: the block is centred
    h = cfg["h_max"]
    for i, t in enumerate(lines):
        x0, x1, y0, y1 = textfit.extents(t, font, 1.0)
        a = textfit.advance(t, font) / 2   # SolidCraft centres each line on its advance
        base = top - 1 - i * ld
        for x in (x0 - a, x1 - a):
            for y in (base + y0, base + y1):
                h = min(h, corner_scale(x, y, cfg))
    return h


def layout(label, font, cfg):
    if "|" in label:
        lines = [s.strip() for s in label.split("|")]
        return lines, fit(lines, font, cfg)
    best = ([label], fit([label], font, cfg))
    words = label.split(" ")
    for i in range(1, len(words)):
        lines = [" ".join(words[:i]), " ".join(words[i:])]
        h = fit(lines, font, cfg)
        if h > best[1] * cfg["two_line_gain"]:
            best = (lines, h)
    return best


def run(args):
    r = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[-600:])


# Raise when a change to this script changes what it writes; edits that do not
# (comments, reporting) then leave every built cap in place.
BUILD_VERSION = 1


def cap_key(row, cfg, design, font):
    """Hash of everything that decides a cap's files: not the label's group or source."""
    h = hashlib.sha256()
    for p in (design, font, textfit.__file__, threemf.__file__):
        h.update(open(p, "rb").read())
    inputs = {k: row[k] for k in ("file", "label", "cap", "letter")}
    h.update(json.dumps([BUILD_VERSION, inputs, cfg], sort_keys=True).encode())
    return h.hexdigest()


def build_one(row, kind, cfg, force):
    design = os.path.join(ROOT, cfg["design"])
    font = os.path.join(ROOT, cfg["font"])
    out3 = os.path.join(BUILD, kind, "3mf", row["file"] + ".3mf")
    outp = os.path.join(BUILD, kind, "preview", row["file"] + ".png")
    meta = os.path.join(BUILD, kind, "meta", row["file"] + ".json")
    key = cap_key(row, cfg, design, font)
    if not force and os.path.exists(meta) and os.path.exists(out3) and os.path.exists(outp):
        m = json.load(open(meta))
        if m.get("key") == key:
            return dict(m, skipped=True)
    lines, h = layout(row["label"], font, cfg)
    script = [
        {"command": "sketch.edit", "params": {"sketch": cfg["sketch"]}},
        {"command": "sketch.edit_text", "params": {
            "link": cfg["text_link"], "font": font, "text": "\n".join(lines),
            "height": round(h, 3), "line_spacing": cfg["line_spacing"]}},
        {"command": "sketch.finish", "params": {}},
    ]
    os.makedirs(os.path.join(BUILD, "tmp"), exist_ok=True)
    with tempfile.TemporaryDirectory(dir=os.path.join(BUILD, "tmp")) as tmp:
        sp = os.path.join(tmp, "script.json")
        json.dump(script, open(sp, "w"))
        raw = os.path.join(tmp, "raw.3mf")
        mj = os.path.join(tmp, "measure.json")
        run(["solidcraft-cli", "run", sp, "--in", design, "--out", raw, "--json-out", mj, "--quiet"])
        bodies = json.load(open(mj))["bodies"]
        threemf.merge(raw, out3, row["file"], {"Cap": row["cap"], "Label": row["letter"]})
        snap = ["solidcraft-cli", "snapshot", sp, "--in", design, "--out", outp,
                "--camera", json.dumps(cfg["camera"]), "--width", "480", "--height", "480",
                "--no-grid", "--no-axes", "--transparent", "--quality", "fine"]
        for b in bodies:
            colour = row["cap"] if b["name"] == "Cap" else row["letter"]
            snap += ["--body", "%s:color=%s" % (b["name"], COLOURS.get(colour, "#cccccc"))]
        run(snap)
    lab = [b for b in bodies if b["name"].startswith("Label")]
    m = dict(file=row["file"], label=row["label"], cap=row["cap"], letter=row["letter"],
             source=row.get("source", ""), lines=lines, cap_height_mm=round(h, 2),
             stem_mm=round(textfit.stem(font, h), 2),
             label_mm3=round(sum(b["volume_mm3"] for b in lab), 3), key=key)
    json.dump(m, open(meta, "w"), indent=1)
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--type", default="round", choices=sorted(CAP_TYPES))
    ap.add_argument("--only", help="comma-separated FILE names")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) // 2))
    ap.add_argument("--force", action="store_true", help="rebuild caps whose inputs did not change")
    a = ap.parse_args()
    cfg = CAP_TYPES[a.type]
    rows = list(csv.DictReader(open(os.path.join(ROOT, "labels", cfg.get("labels", a.type) + ".csv"))))
    files = [r["file"] for r in rows]
    dup = sorted({f for f in files if files.count(f) > 1})
    if dup:
        sys.exit("duplicate file names in labels/%s.csv: %s" % (cfg.get("labels", a.type), ", ".join(dup)))
    if a.only:
        keep = set(a.only.split(","))
        rows = [r for r in rows if r["file"] in keep]
    for d in ("3mf", "preview", "meta"):
        os.makedirs(os.path.join(BUILD, a.type, d), exist_ok=True)

    def one(r):
        try:
            return dict(build_one(r, a.type, cfg, a.force), ok=True)
        except Exception as e:  # report every failure, build the rest
            return dict(file=r["file"], ok=False, error=str(e))

    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(one, rows))
    # Drop outputs of labels that left the list.
    if not a.only:
        live = {r["file"] for r in rows}
        for d, ext in (("3mf", ".3mf"), ("preview", ".png"), ("meta", ".json")):
            for f in os.listdir(os.path.join(BUILD, a.type, d)):
                if f.endswith(ext) and f[: -len(ext)] not in live:
                    os.remove(os.path.join(BUILD, a.type, d, f))
    for r in res:
        if r["ok"]:
            print("ok=1 built=%d file=%s cap_height_mm=%s stem_mm=%s lines=%s" % (
                0 if r.get("skipped") else 1, r["file"], r["cap_height_mm"], r["stem_mm"], "|".join(r["lines"])))
        else:
            print("ok=0 file=%s error=%s" % (r["file"], r["error"].replace("\n", " ")))
    bad = sum(not r["ok"] for r in res)
    print("type=%s caps=%d built=%d skipped=%d failed=%d" % (
        a.type, len(res), sum(r["ok"] and not r.get("skipped") for r in res),
        sum(bool(r.get("skipped")) for r in res), bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
