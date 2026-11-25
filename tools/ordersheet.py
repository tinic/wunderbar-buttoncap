#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Make the order sheet: a US Letter PDF of every cap, with a checkbox and a quantity
field each, grouped as in the gallery. Give it to a bar to tick the caps it wants.

usage: ordersheet.py [--version V] [--out build/order-sheet.pdf]

Reads labels/<type>.csv and the previews of build/<type>/preview/ (run make first).
"""
import argparse, csv, os, sys

from PIL import Image
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import CAP_TYPES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE_W, PAGE_H = letter
M = 36                      # margin, pt
INK = HexColor("#1d2430")
GREY = HexColor("#6b7380")
RULE = HexColor("#d5d9e0")
TYPES = [  # type, title, columns, image box (w, h) in pt
    ("round", "Round caps (10 mm)", 10, (40, 40)),
    ("long", "Long caps (20 x 8 mm)", 5, (88, 40)),
]
# Section band colours, picked in turn.
BANDS = ["#c8102e", "#0057b8", "#00843d", "#6d2077", "#ff6a13", "#1d2430", "#008c95", "#b5651d"]


NAMES = {"T_REX": "T-Rex", "UFO": "UFO", "OK_HAND": "OK Hand", "HFCS_55": "HFCS 55",
         "CO2": "CO2", "IPA": "IPA", "O&C": "O&C"}
SMALL = {"Of", "And", "The"}


def nice(file):
    """PICKLE_JUICE -> Pickle Juice, LEMON_ICON -> Lemon, PILE_OF_POO -> Pile of Poo."""
    if file in NAMES:
        return NAMES[file]
    words = file.replace("_", " ").split()
    if len(words) > 1 and words[-1] == "ICON":
        words = words[:-1]
    out = [w if any(c.isdigit() for c in w) else w.capitalize() for w in words]
    return " ".join(w.lower() if i and w in SMALL else w for i, w in enumerate(out))


def thumb(t, file, cache):
    out = os.path.join(cache, t, file + ".png")
    src = os.path.join(ROOT, "build", t, "preview", file + ".png")
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(src):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        im = Image.open(src).convert("RGBA")
        im = im.crop(im.getbbox())
        im.thumbnail((300, 300), Image.LANCZOS)
        im.save(out)
    return out


def catalog_parts():
    """Commercial label -> first Wunder-Bar part number."""
    parts = {}
    for r in csv.DictReader(open(os.path.join(ROOT, "labels", "wunderbar-catalog.csv"))):
        if r["wunderbar"] and r["label"] not in parts:
            parts[r["label"]] = r["wunderbar"]
    return parts


def fit_text(c, text, font, size, width):
    """The text, shortened with an ellipsis to fit `width`."""
    if c.stringWidth(text, font, size) <= width:
        return text
    while text and c.stringWidth(text + "…", font, size) > width:
        text = text[:-1]
    return text + "…"


class Sheet:
    def __init__(self, path, version):
        self.c = canvas.Canvas(path, pagesize=letter)
        self.c.setTitle("WunderBar button caps: order sheet")
        self.c.setAuthor("wunderbar-buttoncap")
        self.version = version
        self.page = 0
        self.y = 0
        pdfmetrics.registerFont(TTFont("Anton", os.path.join(ROOT, "fonts", "Anton-Regular.ttf")))

    def new_page(self):
        if self.page:
            self.footer()
            self.c.showPage()
        self.page += 1
        c = self.c
        c.setFillColor(INK)
        c.setFont("Anton", 15)
        c.drawString(M, PAGE_H - M - 12, "WUNDERBAR BUTTON CAPS")
        c.setFont("Helvetica", 9)
        c.setFillColor(GREY)
        c.drawRightString(PAGE_W - M, PAGE_H - M - 10, "Order sheet")
        c.setStrokeColor(RULE)
        c.setLineWidth(0.8)
        c.line(M, PAGE_H - M - 20, PAGE_W - M, PAGE_H - M - 20)
        self.y = PAGE_H - M - 32

    def footer(self):
        c = self.c
        c.setFont("Helvetica", 7.5)
        c.setFillColor(GREY)
        c.drawString(M, M - 14, "github.com/tinic/wunderbar-buttoncap" + (" · " + self.version if self.version else ""))
        c.drawRightString(PAGE_W - M, M - 14, "Page %d" % self.page)

    def intro(self, counts):
        c = self.c
        c.setFillColor(INK)
        c.setFont("Helvetica", 9)
        lines = [
            "3D-printed replacement caps for Wunder-Bar M4 bar guns, in two colours: the label is inlaid, so it does not wear off.",
            "Tick the box of each cap you want and write how many. Colours can be changed on request.",
        ]
        for ln in lines:
            c.drawString(M, self.y, ln)
            self.y -= 12
        self.y -= 6
        # Fields.
        fields = [("Bar", 230), ("Contact", 0)]
        x = M
        c.setFont("Helvetica-Bold", 9)
        for label, w in (("Bar name", 250), ("Contact", 0)):
            c.drawString(x, self.y, label)
            lw = c.stringWidth(label, "Helvetica-Bold", 9) + 6
            end = x + w if w else PAGE_W - M
            c.setStrokeColor(GREY)
            c.setLineWidth(0.6)
            c.line(x + lw, self.y - 2, end - 14, self.y - 2)
            x = end
        self.y -= 22
        x = M
        for label, w in (("Date", 150), ("Round buttons per gun", 190), ("Long buttons per gun", 0)):
            c.drawString(x, self.y, label)
            lw = c.stringWidth(label, "Helvetica-Bold", 9) + 6
            end = x + w if w else PAGE_W - M
            c.line(x + lw, self.y - 2, end - 14, self.y - 2)
            x = end
        self.y -= 18
        c.setFont("Helvetica", 7.5)
        c.setFillColor(GREY)
        c.drawString(M, self.y, "%d round caps and %d long caps. Caps marked PH10-74-xxx match a commercial Wunder-Bar cap." % counts)
        self.y -= 14

    def band(self, title, count, colour):
        c = self.c
        c.setFillColor(HexColor(colour))
        c.roundRect(M, self.y - 15, PAGE_W - 2 * M, 17, 3, stroke=0, fill=1)
        c.setFillColor(white)
        c.setFont("Anton", 10.5)
        c.drawString(M + 7, self.y - 10.5, title.upper())
        c.setFont("Helvetica", 8)
        c.drawRightString(PAGE_W - M - 7, self.y - 10, "%d caps" % count)
        self.y -= 23

    def type_title(self, title):
        c = self.c
        c.setFillColor(INK)
        c.setFont("Anton", 13)
        c.drawString(M, self.y - 12, title.upper())
        self.y -= 22

    def cell(self, x, w, h, img, name, sub, imgbox):
        c = self.c
        top = self.y
        iw, ih = imgbox
        im = ImageReader(img)
        pw, ph = im.getSize()
        s = min(iw / pw, ih / ph)
        dw, dh = pw * s, ph * s
        c.drawImage(im, x + (w - dw) / 2, top - ih + (ih - dh) / 2, dw, dh, mask="auto")
        ty = top - ih - 8
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 6.2)
        c.drawCentredString(x + w / 2, ty, fit_text(c, name, "Helvetica-Bold", 6.2, w - 4))
        if sub:
            c.setFillColor(GREY)
            c.setFont("Helvetica", 5.6)
            c.drawCentredString(x + w / 2, ty - 7, fit_text(c, sub, "Helvetica", 5.6, w - 4))
        # Checkbox and quantity.
        by = top - h + 7
        bx = x + w / 2 - 20
        c.setStrokeColor(INK)
        c.setLineWidth(0.7)
        c.rect(bx, by, 8, 8, stroke=1, fill=0)
        c.setFillColor(GREY)
        c.setFont("Helvetica", 5.6)
        c.drawString(bx + 11, by + 1.5, "Qty")
        c.setStrokeColor(GREY)
        c.setLineWidth(0.5)
        c.line(bx + 22, by + 0.5, bx + 40, by + 0.5)

    def grid(self, items, cols, imgbox):
        w = (PAGE_W - 2 * M) / cols
        h = imgbox[1] + 32
        for i in range(0, len(items), cols):
            if self.y - h < M + 4:
                self.new_page()
            for k, it in enumerate(items[i:i + cols]):
                self.cell(M + k * w, w, h, *it, imgbox)
            self.y -= h
        self.y -= 8

    def save(self):
        self.footer()
        self.c.save()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "order-sheet.pdf"))
    a = ap.parse_args()
    cache = os.path.join(ROOT, "build", "ordersheet")
    parts = catalog_parts()
    data = []
    for t, title, cols, box in TYPES:
        rows = list(csv.DictReader(open(os.path.join(ROOT, "labels", CAP_TYPES[t].get("labels", t) + ".csv"))))
        groups = {}
        for r in rows:
            if r.get("font"):
                name, sub = nice(r["file"]), ""
            elif r["source"] == "wunderbar":
                name, sub = r["label"], parts.get(r["label"], "")
            else:
                name = nice(r["file"])
                code = r["label"].replace("|", " ")
                sub = code if code.upper() != name.upper() else ""
            groups.setdefault(r["group"], []).append((thumb(t, r["file"], cache), name, sub))
        data.append((t, title, cols, box, groups))

    sheet = Sheet(a.out, a.version)
    sheet.new_page()
    sheet.intro(tuple(sum(len(v) for v in g.values()) for _, _, _, _, g in data))
    band = 0
    for t, title, cols, box, groups in data:
        if sheet.y - 60 < M:
            sheet.new_page()
        sheet.type_title(title)
        for g, items in groups.items():
            # Keep a section's band with its first row.
            if sheet.y - 23 - (box[1] + 32) < M + 4:
                sheet.new_page()
            sheet.band(g, len(items), BANDS[band % len(BANDS)])
            band += 1
            sheet.grid(items, cols, box)
    sheet.save()
    print("ordersheet=%s pages=%d caps=%d" % (a.out, sheet.page, sum(
        len(v) for _, _, _, _, g in data for v in g.values())))


if __name__ == "__main__":
    main()
