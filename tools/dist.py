#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pack the release archive: dist/wunderbar-buttoncap-<version>.zip

usage: dist.py VERSION [--type round ...]
The archive holds, per cap type: 3mf/, preview/, index.html, contact-sheet.png and
the labels CSV, plus a README.txt.
"""
import argparse, os, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import CAP_TYPES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

README = """WunderBar bar gun button caps {version}
https://github.com/tinic/wunderbar-buttoncap

Open {first}/index.html to see every cap. Each 3MF is one object with two
parts: "Cap" and "Label". Print the label face down. In the slicer, give the
Label part the letter colour and the Cap part the cap colour. The label is a
0.4 mm inlay flush with the face.

Fits Wunder-Bar M4 bar guns:
  round/         round button caps (as PH10-74-xxx)
  long/          long button PH10-76
  long-ph10-32/  long button PH10-76 with the two snap pins for PH10-32

The caps (3MF files and previews) are licensed under CERN-OHL-P-2.0
(LICENSE-CERN-OHL-P.txt). Product names on the labels are trademarks of their
owners; the labels only name the drink that a button dispenses.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version")
    ap.add_argument("--type", action="append")
    a = ap.parse_args()
    types = a.type or ["round"]
    name = "wunderbar-buttoncap-%s" % a.version
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    path = os.path.join(ROOT, "dist", name + ".zip")
    count = 0
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name + "/README.txt", README.format(version=a.version, first=types[0]))
        z.write(os.path.join(ROOT, "LICENSE-CERN-OHL-P.txt"), name + "/LICENSE-CERN-OHL-P.txt")
        for t in types:
            base = os.path.join(ROOT, "build", t)
            z.write(os.path.join(ROOT, "labels", CAP_TYPES[t].get("labels", t) + ".csv"), "%s/%s/labels.csv" % (name, t))
            for f in ("index.html", "contact-sheet.png"):
                z.write(os.path.join(base, f), "%s/%s/%s" % (name, t, f))
            for d in ("3mf", "preview"):
                for f in sorted(os.listdir(os.path.join(base, d))):
                    z.write(os.path.join(base, d, f), "%s/%s/%s/%s" % (name, t, d, f))
                    count += d == "3mf"
    print("archive=%s caps=%d bytes=%d" % (path, count, os.path.getsize(path)))


if __name__ == "__main__":
    main()
