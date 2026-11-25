# SPDX-License-Identifier: MIT
# Build every cap, the preview gallery and the release archive.
#   make            3MF + preview PNG per label (only what changed)
#   make gallery    build/<type>/index.html and contact-sheet.png
#   make ordersheet build/order-sheet.pdf: every cap with a checkbox, for bars to order from
#   make docs       docs/<type>-<group>.jpg and the "All caps" part of README.md
#   make dist VERSION=v0.1.0
#   make release VERSION=v0.1.0   (draft GitHub release with the archive)
TYPES   ?= round long
DOC_TYPES ?= round long
VERSION ?= dev
PYTHON  ?= .venv/bin/python
JOBS    ?= 6

.PHONY: all caps gallery docs ordersheet dist release clean venv

all: gallery

venv: .venv/.ok
.venv/.ok: requirements.txt
	python3 -m venv .venv
	.venv/bin/pip install -q -r requirements.txt
	touch $@

caps: venv
	@for t in $(TYPES); do $(PYTHON) tools/build.py --type $$t --jobs $(JOBS) | tail -1 || exit 1; done

gallery: caps
	@for t in $(TYPES); do $(PYTHON) tools/gallery.py --type $$t --version $(VERSION) || exit 1; done

docs: caps
	@for t in $(DOC_TYPES); do $(PYTHON) tools/gallery.py --type $$t --version $(VERSION) --docs || exit 1; done

ordersheet: gallery
	$(PYTHON) tools/ordersheet.py --version $(VERSION)

dist: gallery ordersheet
	$(PYTHON) tools/dist.py $(VERSION) $(foreach t,$(TYPES),--type $(t))

release: dist
	@for t in $(TYPES); do cp build/$$t/contact-sheet.png dist/$$t-contact-sheet.png; done
	gh release create $(VERSION) dist/wunderbar-buttoncap-$(VERSION).zip \
	  $(foreach t,$(TYPES),dist/$(t)-contact-sheet.png) build/order-sheet.pdf \
	  --draft --title "wunderbar-buttoncap $(VERSION)" --notes-file RELEASE_NOTES.md

clean:
	rm -rf build dist
