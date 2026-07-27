#!/bin/bash
set -euo pipefail

# hyperresearch のローカルセットアップ (macOS / Linux)。
# リモート (Claude Code on the web) は .claude/hooks/session-start.sh が自動処理するので、
# このスクリプトは手元のマシンで一度だけ実行すればよい。何度実行しても安全。

if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
  echo "リモート環境では .claude/hooks/session-start.sh が自動セットアップするため、このスクリプトは不要です。" >&2
  echo "(ここで patchright install を走らせるとブラウザ設定を壊すので中断します)" >&2
  exit 1
fi

PY="${PYTHON:-python3}"

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "エラー: python3 が見つかりません。Python 3.11〜3.13 をインストールしてください。" >&2
  exit 1
fi

ver=$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
case "$ver" in
  3.11|3.12|3.13) ;;
  *)
    echo "エラー: Python $ver は未対応です (hyperresearch は 3.11〜3.13)。" >&2
    echo "  例: pyenv install 3.13 / uv venv -p 3.13 を使い、PYTHON=<path> $0 で再実行してください。" >&2
    exit 1
    ;;
esac

# 1. hyperresearch CLI
if ! command -v hyperresearch >/dev/null 2>&1; then
  echo "hyperresearch をインストールします..."
  "$PY" -m pip install hyperresearch || {
    echo "pip install が失敗しました (PEP 668 の externally-managed 環境の可能性)。" >&2
    echo "  pipx install hyperresearch  または  uv tool install hyperresearch  を試してください。" >&2
    exit 1
  }
fi

actual=$(command -v hyperresearch)

# 2. リポジトリにコミット済みのスキル/CLAUDE.md は CLI を /usr/local/bin/hyperresearch の
#    固定パスで呼ぶ (マシンごとのパス差分を吸収するため)。実体をそこへリンクする。
target=/usr/local/bin/hyperresearch
if [ ! -x "$target" ]; then
  echo "$target -> $actual をリンクします..."
  if [ -w "$(dirname "$target")" ]; then
    ln -sf "$actual" "$target"
  else
    sudo ln -sf "$actual" "$target"
  fi
fi

# 3. フェッチ用ブラウザ (crawl4ai/patchright が使う chromium)
if ! "$PY" - <<'CHECK' 2>/dev/null
import sys
from patchright.sync_api import sync_playwright
with sync_playwright() as p:
    sys.exit(0 if __import__("os").path.exists(p.chromium.executable_path) else 1)
CHECK
then
  echo "patchright 用の chromium をダウンロードします..."
  "$PY" -m patchright install chromium
fi

echo
echo "セットアップ完了: $("$target" --version 2>&1 | tail -1)"
echo "このリポジトリで Claude Code を開き、/hyperresearch <クエリ> を実行できます。"
