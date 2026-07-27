# text

執筆用リポジトリ。[hyperresearch](https://github.com/jordan-gibbs/hyperresearch) による deep research パイプラインがセットアップ済みで、Claude Code から `/hyperresearch <クエリ>` で調査レポートを生成できます。

## hyperresearch のセットアップ

### Claude Code on the web（リモート）

何もしなくてよい。`.claude/hooks/session-start.sh` がセッション開始時に CLI のインストールとブラウザ設定を自動で行います。

ただし調査の実行（Web フェッチ）には、環境のネットワークポリシーで一般サイトへのアクセスが許可されている必要があります。

### ローカル（macOS / Linux）

一度だけ実行:

```bash
./scripts/setup-local.sh
```

やっていること:

1. `pip install hyperresearch`（Python 3.11〜3.13 が必要）
2. `/usr/local/bin/hyperresearch` へのシンボリックリンク作成 — コミット済みのスキルファイル群は CLI をこの固定パスで呼ぶため（書き込みに sudo を求められることがあります）
3. フェッチ用 chromium のダウンロード（`patchright install chromium`）

pip が externally-managed エラーになる場合は `pipx install hyperresearch` か `uv tool install hyperresearch` を使ってください（スクリプトはリンク作成時に PATH 上の実体を拾います）。

### 使い方

このリポジトリで Claude Code を開いて:

```
/hyperresearch 調べたいことを書く
```

vault の状態確認: `/usr/local/bin/hyperresearch status -j`
スケールギア切替: `/usr/local/bin/hyperresearch profile use <full|premier>`

詳細な運用ルールは `CLAUDE.md` を参照。
