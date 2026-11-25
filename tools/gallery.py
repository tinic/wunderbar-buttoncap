#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Make the preview gallery of one cap type from the built caps.

usage: gallery.py [--type round] [--version V] [--docs]

Always writes build/<type>/index.html and build/<type>/contact-sheet.png.
With --docs it also writes one sheet per label group to docs/<type>-<group>.jpg and
puts the list of sheets into README.md between the "caps:<type>:start" and
"caps:<type>:end" markers.
"""
import argparse, csv, html, json, os, re, sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import CAP_TYPES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The caps of docs/sample.png, the picture at the top of the README.
SAMPLE = ["PICKLE_JUICE", "COFFEE", "CAMPARI", "OJ", "COKE", "GIN", "IRISH_WHISKEY", "SPICY_GINGER",
          "PASSION_FRUIT", "TONIC", "DIET", "SPRITE", "WILD_CHERRY", "BMARY", "B"]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def sheet(items, base, cols, tile, caption_px, out, fmt):
    """Tiles `tile` wide; each row as tall as its tallest cap, with the caption under it."""
    font = ImageFont.truetype(os.path.join(ROOT, "fonts", "Anton-Regular.ttf"), caption_px) if caption_px else None
    cap_h = int(caption_px * 1.6)
    thumbs = []
    for m in items:
        im = Image.open(os.path.join(base, "preview", m["file"] + ".png")).convert("RGBA")
        im = im.crop(im.getbbox())  # the cap fills the tile
        im.thumbnail((int(tile * 0.9), int(tile * 0.9)), Image.LANCZOS)
        thumbs.append(im)
    rows = [list(range(i, min(i + cols, len(items)))) for i in range(0, len(items), cols)]
    heights = [max(thumbs[i].height for i in r) + int(tile * 0.1) for r in rows]
    im_out = Image.new("RGB", (cols * tile, sum(heights) + cap_h * len(rows)), "#eceef1")
    d = ImageDraw.Draw(im_out)
    y = 0
    for r, rh in zip(rows, heights):
        for k, i in enumerate(r):
            x = k * tile
            im = thumbs[i]
            im_out.paste(im, (x + (tile - im.width) // 2, y + (rh - im.height) // 2), im)
            if font:
                d.text((x + tile / 2, y + rh), items[i]["file"].replace("_", " "), fill="#333333",
                       font=font, anchor="ma")
        y += rh + cap_h
    if fmt == "jpg":
        im_out.save(out, quality=82, optimize=True, progressive=True)
    else:
        im_out.save(out, optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", default="round")
    ap.add_argument("--version", default="")
    ap.add_argument("--docs", action="store_true")
    a = ap.parse_args()
    base = os.path.join(ROOT, "build", a.type)
    labels = CAP_TYPES[a.type].get("labels", a.type)
    rows = list(csv.DictReader(open(os.path.join(ROOT, "labels", labels + ".csv"))))
    caps = []
    for r in rows:
        mp = os.path.join(base, "meta", r["file"] + ".json")
        if not os.path.exists(mp):
            raise SystemExit("missing build output for %s: run build.py first" % r["file"])
        caps.append(dict(json.load(open(mp)), group=r.get("group") or "Other"))
    groups = []
    for c in caps:
        if c["group"] not in groups:
            groups.append(c["group"])
    by_group = {g: [c for c in caps if c["group"] == g] for g in groups}

    sheet(caps, base, 12, 240, 20, os.path.join(base, "contact-sheet.png"), "png")

    # HTML gallery: opens from the release archive, no server needed.
    sections = []
    for g in groups:
        cards = []
        for m in by_group[g]:
            cards.append(
                '<figure data-q="{q}"><img src="preview/{f}.png" alt="{lab}" loading="lazy">'
                '<figcaption><b>{f}</b><span>{cap} cap, {let} letters &middot; {h} mm</span>'
                '<a href="3mf/{f}.3mf">3MF</a></figcaption></figure>'.format(
                    q=html.escape((m["file"] + " " + m["label"] + " " + g).lower()), f=html.escape(m["file"]),
                    lab=html.escape(m["label"].replace("|", " ")), cap=html.escape(m["cap"]),
                    let=html.escape(m["letter"]), h=m["cap_height_mm"]))
        sections.append('<section><h2>%s <small>%d</small></h2><div class="grid">%s</div></section>' % (
            html.escape(g), len(by_group[g]), "\n".join(cards)))
    title = "WunderBar button caps (%s)%s" % (a.type, " " + a.version if a.version else "")
    page = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{font:15px/1.4 system-ui,sans-serif;margin:0;background:#eceef1;color:#222}}
header{{position:sticky;top:0;z-index:1;background:#fff;padding:12px 20px;box-shadow:0 1px 4px #0002;display:flex;gap:16px;align-items:center;flex-wrap:wrap}}
h1{{font-size:18px;margin:0}} input{{font:inherit;padding:6px 10px;width:220px}}
section{{padding:4px 20px 12px}} h2{{font-size:16px;margin:16px 0 8px}} h2 small{{color:#888;font-weight:normal}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}}
figure{{margin:0;background:#fff;border-radius:8px;padding:8px;text-align:center}}
img{{width:100%;height:auto}} figcaption{{display:flex;flex-direction:column;gap:2px}}
figcaption span{{color:#666;font-size:12px}} a{{color:#0057b8}}
</style>
<header><h1>{title}</h1><span>{n} caps</span>
<input type="search" placeholder="Filter" oninput="const q=this.value.toLowerCase();for(const f of document.querySelectorAll('figure'))f.hidden=!f.dataset.q.includes(q);for(const s of document.querySelectorAll('section'))s.hidden=!s.querySelector('figure:not([hidden])')">
</header>
{sections}
</html>
""".format(title=html.escape(title), n=len(caps), sections="\n".join(sections))
    open(os.path.join(base, "index.html"), "w").write(page)

    if a.docs:
        docs = os.path.join(ROOT, "docs")
        os.makedirs(docs, exist_ok=True)
        live = set()
        md = []
        for g in groups:
            name = "%s-%s.jpg" % (a.type, slug(g))
            live.add(name)
            sheet(by_group[g], base, 8, 200, 20, os.path.join(docs, name), "jpg")
            md.append("### %s (%d)\n\n![%s](docs/%s)\n" % (g, len(by_group[g]), g, name))
        sample = [c for f in SAMPLE for c in caps if c["file"] == f]
        if sample and a.type == "round":
            sheet(sample, base, 5, 240, 0, os.path.join(docs, "sample.png"), "png")
        for f in os.listdir(docs):
            if f.startswith(a.type + "-") and f.endswith(".jpg") and f not in live:
                os.remove(os.path.join(docs, f))
        readme = os.path.join(ROOT, "README.md")
        text = open(readme).read()
        start, end = "<!-- caps:%s:start -->" % a.type, "<!-- caps:%s:end -->" % a.type
        if start in text and end in text:
            head, rest = text.split(start, 1)
            _, tail = rest.split(end, 1)
            note = "%d caps. Generated by `make docs` from `labels/%s.csv`.\n\n" % (len(caps), labels)
            md = [m.replace("### ", "#### ") for m in md]
            text = head + start + "\n" + note + "\n".join(md) + end + tail
            open(readme, "w").write(text)
    print("type=%s caps=%d groups=%d gallery=%s docs=%d" % (
        a.type, len(caps), len(groups), os.path.join(base, "index.html"), int(a.docs)))


if __name__ == "__main__":
    main()
