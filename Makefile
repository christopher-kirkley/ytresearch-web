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

# --- launchd service (macOS LaunchAgent) ---
LABEL := com.ck.ytresearch-web
LAUNCH_AGENTS := $(HOME)/Library/LaunchAgents
PLIST := $(LAUNCH_AGENTS)/$(LABEL).plist
LOG := $(HOME)/Library/Logs/ytresearch-web.log
UID := $(shell id -u)

.PHONY: run serve test sync install-service uninstall-service service-status service-logs

sync:
	uv sync

# Development server: auto-reload, single-threaded. Use `serve` for the real one.
run:
	uv run $(OVERRIDE) flask --app ytresearch_web.app run --port $(PORT)

# Production-style server (waitress), same as the launchd service runs.
serve:
	uv run $(OVERRIDE) ytresearch-web

test:
	uv run $(OVERRIDE) pytest

# Install + start the boot service (renders the plist with this checkout's paths).
install-service:
	@test -x "$(PWD)/.venv/bin/ytresearch-web" || { echo "Run 'uv sync' first (.venv/bin/ytresearch-web missing)"; exit 1; }
	@mkdir -p "$(LAUNCH_AGENTS)" "$(HOME)/Library/Logs"
	sed -e 's|__LABEL__|$(LABEL)|g' \
	    -e 's|__VENV_BIN__|$(PWD)/.venv/bin|g' \
	    -e 's|__WORKDIR__|$(PWD)|g' \
	    -e 's|__LOG__|$(LOG)|g' \
	    deploy/ytresearch-web.plist.template > "$(PLIST)"
	-launchctl bootout gui/$(UID)/$(LABEL) 2>/dev/null
	launchctl bootstrap gui/$(UID) "$(PLIST)"
	launchctl kickstart -k gui/$(UID)/$(LABEL)
	@echo "Installed. Serving on http://127.0.0.1:$(PORT) — logs: $(LOG)"

uninstall-service:
	-launchctl bootout gui/$(UID)/$(LABEL) 2>/dev/null
	rm -f "$(PLIST)"
	@echo "Service removed."

service-status:
	@launchctl print gui/$(UID)/$(LABEL) 2>/dev/null | grep -E '^\s*(state|pid) =' || echo "not loaded"

service-logs:
	@tail -n 50 -f "$(LOG)"
