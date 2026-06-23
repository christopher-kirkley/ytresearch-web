# Local development convenience wrapper.
#
# By default the `ytresearch` dependency is pulled from GitHub (pinned in
# uv.lock), so a plain `uv sync` works on any machine with no local checkout.
#
# To develop `ytresearch` and `ytresearch-web` side-by-side, point
# YTRESEARCH_SRC at a local checkout of the ytresearch repo. The targets below
# then layer it in as an editable install via `uv run --with-editable`, without
# touching pyproject.toml or uv.lock (so the override never gets committed).
#
# Set it per-machine either by exporting in your shell:
#     export YTRESEARCH_SRC=/path/to/ytresearch
# or by adding a line to the gitignored .env file:
#     YTRESEARCH_SRC=/path/to/ytresearch
#
# An exported shell value wins; otherwise we read it from .env if present.
YTRESEARCH_SRC ?= $(shell grep -s '^YTRESEARCH_SRC=' .env | cut -d= -f2-)
OVERRIDE := $(if $(strip $(YTRESEARCH_SRC)),--with-editable $(YTRESEARCH_SRC),)

PORT ?= 5001

.PHONY: run test sync

sync:
	uv sync

run:
	uv run $(OVERRIDE) flask --app ytresearch_web.app run --port $(PORT)

test:
	uv run $(OVERRIDE) pytest
