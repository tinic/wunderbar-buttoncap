#!/usr/bin/env python3
"""Make the preview gallery of one cap type: build/<type>/index.html and contact-sheet.png.

usage: gallery.py [--type round]
"""
import argparse, csv, html, json, os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TILE = 240
COLS = 12


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", default="round")
    ap.add_argument("--version", default="")
    a = ap.parse_args()
    base = os.path.join(ROOT, "build", a.type)
    rows = list(csv.DictReader(open(os.path.join(ROOT, "labels", a.type + ".csv"))))
    metas = []
    for r in rows:
        mp = os.path.join(base, "meta", r["file"] + ".json")
        if not os.path.exists(mp):
            raise SystemExit("missing build output for %s: run build.py first" % r["file"])
        metas.append(json.load(open(mp)))

    # Contact sheet.
    font = ImageFont.truetype(os.path.join(ROOT, "fonts", "Anton-Regular.ttf"), 20)
    n = len(metas)
    rows_n = (n + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * TILE, rows_n * (TILE + 34)), "#eceef1")
    d = ImageDraw.Draw(sheet)
    for i, m in enumerate(metas):
        x, y = (i % COLS) * TILE, (i // COLS) * (TILE + 34)
        im = Image.open(os.path.join(base, "preview", m["file"] + ".png")).convert("RGBA")
        im.thumbnail((TILE, TILE))
        sheet.paste(im, (x + (TILE - im.width) // 2, y), im)
        d.text((x + TILE / 2, y + TILE + 2), m["file"], fill="#333333", font=font, anchor="ma")
    sheet.save(os.path.join(base, "contact-sheet.png"), optimize=True)

    # HTML gallery: opens from the release archive, no server needed.
    cards = []
    for m in metas:
        cards.append(
            '<figure data-q="{q}"><img src="preview/{f}.png" alt="{lab}" loading="lazy">'
            '<figcaption><b>{f}</b><span>{cap} cap, {let} letters &middot; {h} mm</span>'
            '<a href="3mf/{f}.3mf">3MF</a></figcaption></figure>'.format(
                q=html.escape((m["file"] + " " + m["label"]).lower()), f=html.escape(m["file"]),
                lab=html.escape(m["label"].replace("|", " ")), cap=html.escape(m["cap"]),
                let=html.escape(m["letter"]), h=m["cap_height_mm"]))
    title = "WunderBar button caps (%s)%s" % (a.type, " " + a.version if a.version else "")
    page = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{font:15px/1.4 system-ui,sans-serif;margin:0;background:#eceef1;color:#222}}
header{{position:sticky;top:0;background:#fff;padding:12px 20px;box-shadow:0 1px 4px #0002;display:flex;gap:16px;align-items:center;flex-wrap:wrap}}
h1{{font-size:18px;margin:0}} input{{font:inherit;padding:6px 10px;width:220px}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px;padding:20px}}
figure{{margin:0;background:#fff;border-radius:8px;padding:8px;text-align:center}}
img{{width:100%;height:auto}} figcaption{{display:flex;flex-direction:column;gap:2px}}
figcaption span{{color:#666;font-size:12px}} a{{color:#0057b8}}
</style>
<header><h1>{title}</h1><span>{n} caps</span>
<input type="search" placeholder="Filter" oninput="for(const f of document.querySelectorAll('figure'))f.hidden=!f.dataset.q.includes(this.value.toLowerCase())">
</header>
<main>
{cards}
</main>
</html>
""".format(title=html.escape(title), n=n, cards="\n".join(cards))
    open(os.path.join(base, "index.html"), "w").write(page)
    print("type=%s caps=%d gallery=%s sheet=%s" % (a.type, n, os.path.join(base, "index.html"),
                                                    os.path.join(base, "contact-sheet.png")))


if __name__ == "__main__":
    main()
