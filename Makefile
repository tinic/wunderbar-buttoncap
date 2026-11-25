# Build every cap, the preview gallery and the release archive.
#   make            3MF + preview PNG per label (only what changed)
#   make gallery    build/<type>/index.html and contact-sheet.png
#   make dist VERSION=v0.1.0
#   make release VERSION=v0.1.0   (draft GitHub release with the archive)
TYPES   ?= round
VERSION ?= dev
PYTHON  ?= .venv/bin/python
JOBS    ?= 6

.PHONY: all caps gallery dist release clean venv

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

dist: gallery
	$(PYTHON) tools/dist.py $(VERSION) $(foreach t,$(TYPES),--type $(t))

release: dist
	gh release create $(VERSION) dist/wunderbar-buttoncap-$(VERSION).zip \
	  $(foreach t,$(TYPES),build/$(t)/contact-sheet.png#$(t)-contact-sheet.png) \
	  --draft --title "wunderbar-buttoncap $(VERSION)" --notes-file RELEASE_NOTES.md

clean:
	rm -rf build dist
