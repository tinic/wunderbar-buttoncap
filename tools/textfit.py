# SPDX-License-Identifier: MIT
"""Measure a label's outline extents in a font, in mm at a given capital height."""
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen

import threading

_cache = {}
_lock = threading.Lock()


def _font(path):
    # Loaded whole (lazy=False) and once: fontTools' lazy table loading is not thread-safe.
    with _lock:
        if path not in _cache:
            _cache[path] = TTFont(path, lazy=False)
        return _cache[path]

def extents(text, font_path, cap_h=1.0):
    """Return (xmin, xmax, ymin, ymax) of `text` laid on baseline y=0, x from 0, in mm."""
    f = _font(font_path)
    gs = f.getGlyphSet()
    cmap = f.getBestCmap()
    scale = cap_h / f['OS/2'].sCapHeight
    hmtx = f['hmtx']
    x = 0.0
    xmin = ymin = float('inf'); xmax = ymax = float('-inf')
    for ch in text:
        g = cmap.get(ord(ch))
        if g is None:
            raise KeyError(f"{ch!r} not in font {font_path}")
        bp = BoundsPen(gs)
        gs[g].draw(bp)
        if bp.bounds:
            a, b, c, d = bp.bounds
            xmin = min(xmin, x + a); xmax = max(xmax, x + c)
            ymin = min(ymin, b); ymax = max(ymax, d)
        x += hmtx[g][0]
    return xmin * scale, xmax * scale, ymin * scale, ymax * scale


def stem(font_path, cap_h=1.0, ch="H"):
    """Width of the first vertical stem of `ch` at half capital height, in mm."""
    from fontTools.pens.pointInsidePen import PointInsidePen
    f = _font(font_path)
    gs = f.getGlyphSet()
    g = f.getBestCmap()[ord(ch)]
    capu = f['OS/2'].sCapHeight
    y = capu * 0.28
    adv = f['hmtx'][g][0]
    step = adv / 2000.0
    inside = False
    start = None
    x = 0.0
    while x < adv:
        p = PointInsidePen(gs, (x, y))
        gs[g].draw(p)
        if p.getResult() and not inside:
            inside, start = True, x
        elif not p.getResult() and inside:
            return (x - start) * cap_h / capu
        x += step
    return 0.0


def advance(text, font_path, cap_h=1.0):
    """Sum of the glyph advances of `text`, in mm at capital height cap_h (no kerning, as SolidCraft)."""
    f = _font(font_path)
    cm = f.getBestCmap()
    return sum(f["hmtx"][cm[ord(c)]][0] for c in text) * cap_h / f["OS/2"].sCapHeight
