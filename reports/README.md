# Citadel AI ウェブ分析 週次レポート

Plausible Analytics のデータから、citadel-ai.com の週次アクセス解析レポートを
自動生成する仕組み。毎週月曜 09:07 (JST) に GitHub Actions
([`weekly-report.yml`](../.github/workflows/weekly-report.yml)) が実行される。

## 出力

| ファイル | 内容 |
|---|---|
| [`latest.md`](latest.md) | 最新レポートの要約 (GitHub上でそのまま読める) |
| [`latest.html`](latest.html) | 最新レポートの詳細版 (チャート付き・ブラウザで開く) |
| `history/YYYY-MM-DD.html` | 週ごとのアーカイブ (対象週の日曜日付) |

## セットアップ

リポジトリの **Settings → Secrets and variables → Actions** で以下を登録する:

| Secret | 必須 | 説明 |
|---|---|---|
| `PLAUSIBLE_API_KEY` | ✅ | Plausible の Stats API キー (Plausible: Settings → API Keys で発行) |
| `SLACK_WEBHOOK_URL` | 任意 | Slack Incoming Webhook のURL。設定すると #sales-and-marketing など任意のチャンネルに要約を自動投稿 |

スケジュール実行はリポジトリの**デフォルトブランチ**にあるワークフローのみ有効。
手動テストは Actions タブ → "Weekly web analytics report" → Run workflow。

## 対象期間の考え方

実行日 (月曜) の前週月曜〜日曜を対象とし、そのさらに前の週と比較して
前週比を算出する。日別チャートは対象週と前週を同じ曜日軸で重ねて表示する。
