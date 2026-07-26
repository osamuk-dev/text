#!/bin/bash
set -euo pipefail

# Only needed in Claude Code on the web — local machines set up hyperresearch
# themselves via `pip install hyperresearch && hyperresearch install`.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# hyperresearch CLI (provides /usr/local/bin/hyperresearch).
# --ignore-installed works around the debian-managed cryptography package,
# which pip cannot uninstall (missing RECORD file).
if ! command -v hyperresearch >/dev/null 2>&1; then
  pip install --quiet --ignore-installed cryptography hyperresearch
fi

# hyperresearch fetches pages through crawl4ai/patchright, which looks for its
# own pinned chromium build. The remote environment pre-installs Playwright
# browsers under /opt/pw-browsers and blocks browser downloads
# (cdn.playwright.dev is not on the egress allowlist), so link the paths
# patchright expects to the pre-installed build instead.
PW="${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"
if [ -d "$PW" ]; then
  revs=$(python3 - <<'PY'
import json, os
import patchright
p = os.path.join(os.path.dirname(patchright.__file__), "driver", "package", "browsers.json")
browsers = {b["name"]: b["revision"] for b in json.load(open(p))["browsers"]}
print(browsers.get("chromium-headless-shell", ""), browsers.get("chromium", ""))
PY
)
  shell_rev=$(echo "$revs" | cut -d' ' -f1)
  chromium_rev=$(echo "$revs" | cut -d' ' -f2)

  existing_shell=$(ls "$PW"/chromium_headless_shell-*/chrome-linux/headless_shell 2>/dev/null | head -1 || true)
  shell_target="$PW/chromium_headless_shell-$shell_rev/chrome-headless-shell-linux64/chrome-headless-shell"
  if [ -n "$shell_rev" ] && [ -n "$existing_shell" ] && [ ! -e "$shell_target" ]; then
    mkdir -p "$(dirname "$shell_target")"
    ln -sf "$existing_shell" "$shell_target"
  fi

  existing_chrome=$(ls "$PW"/chromium-*/chrome-linux/chrome 2>/dev/null | head -1 || true)
  chrome_target="$PW/chromium-$chromium_rev/chrome-linux/chrome"
  if [ -n "$chromium_rev" ] && [ -n "$existing_chrome" ] && [ ! -e "$chrome_target" ]; then
    mkdir -p "$(dirname "$chrome_target")"
    ln -sf "$existing_chrome" "$chrome_target"
  fi
fi

# The vault sqlite index is gitignored; rebuild it from the markdown notes.
if [ -d "$CLAUDE_PROJECT_DIR/research" ]; then
  (cd "$CLAUDE_PROJECT_DIR" && hyperresearch sync --json >/dev/null 2>&1) || true
fi
