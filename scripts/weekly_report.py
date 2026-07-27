#!/usr/bin/env python3
"""Citadel AI ウェブ分析 週次レポート生成 (Plausible Stats API v2)

毎週月曜に GitHub Actions から実行される。前週 (月〜日) のアクセス解析を
取得し、reports/latest.html (詳細レポート) と reports/latest.md (要約) を
生成する。SLACK_WEBHOOK_URL が設定されていれば要約を Slack に投稿する。

必要な環境変数:
  PLAUSIBLE_API_KEY  Plausible Stats API キー (必須)
  SLACK_WEBHOOK_URL  Slack Incoming Webhook (任意)
  REPORT_LINK        Slack 投稿に載せるレポートURL (任意)
"""

import datetime as dt
import html
import json
import os
import sys
import urllib.error
import urllib.request

API_URL = "https://plausible.io/api/v2/query"
SITE_CANDIDATES = ["citadel-ai.com", "www.citadel-ai.com"]
METRICS = ["visitors", "visits", "pageviews", "bounce_rate", "visit_duration"]
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")


def api_query(payload: dict) -> list:
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['PLAUSIBLE_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.load(res)["results"]
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Plausible API {e.code}: {body}") from e


def resolve_site_id() -> str:
    last_error = None
    for site_id in SITE_CANDIDATES:
        try:
            api_query({"site_id": site_id, "metrics": ["visitors"], "date_range": "7d"})
            return site_id
        except RuntimeError as e:
            last_error = e
    raise RuntimeError(f"site_id を解決できませんでした ({SITE_CANDIDATES}): {last_error}")


def aggregate(site_id: str, start: dt.date, end: dt.date) -> dict:
    rows = api_query({
        "site_id": site_id,
        "metrics": METRICS,
        "date_range": [start.isoformat(), end.isoformat()],
    })
    values = rows[0]["metrics"] if rows else [0] * len(METRICS)
    return dict(zip(METRICS, values))


def breakdown(site_id: str, dimension: str, start: dt.date, end: dt.date,
              metrics=("visitors",), limit=10) -> list:
    try:
        return api_query({
            "site_id": site_id,
            "metrics": list(metrics),
            "date_range": [start.isoformat(), end.isoformat()],
            "dimensions": [dimension],
            "pagination": {"limit": limit},
        })
    except RuntimeError as e:
        print(f"warning: {dimension} の取得に失敗: {e}", file=sys.stderr)
        return []


def daily_series(site_id: str, start: dt.date, end: dt.date) -> dict:
    rows = api_query({
        "site_id": site_id,
        "metrics": ["visitors"],
        "date_range": [start.isoformat(), end.isoformat()],
        "dimensions": ["time:day"],
    })
    return {r["dimensions"][0]: r["metrics"][0] for r in rows}


def pct_change(cur: float, prev: float):
    if prev == 0:
        return None
    return (cur - prev) / prev * 100


def fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds or 0), 60)
    return f"{m}分{s:02d}秒"


def fmt_delta(change, lower_is_better=False) -> str:
    if change is None:
        return "—"
    if abs(change) < 0.05:
        return "±0.0%"
    arrow = "▲" if change > 0 else "▼"
    return f"{arrow} {abs(change):.1f}%"


def delta_class(change, lower_is_better=False) -> str:
    if change is None or abs(change) < 0.05:
        return "flat"
    good = (change < 0) if lower_is_better else (change > 0)
    return "up" if good else "down"


def build_chart_svg(days: list, daily: dict) -> str:
    """対象週と前週の日別訪問者数を重ねた折れ線チャート (SVG)。

    daily は前週初日〜対象週末日の14日分 {date: visitors}。前週の値は
    同じ曜日 (7日前) の日付を引いて重ねる。"""
    w, h = 720, 240
    pad_l, pad_r, pad_t, pad_b = 44, 64, 16, 30
    plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b
    cur = [daily.get(d.isoformat(), 0) for d in days]
    prev = [daily.get((d - dt.timedelta(days=7)).isoformat(), 0) for d in days]
    y_max = max(cur + prev + [1])

    def x(i):
        return pad_l + plot_w * i / (len(days) - 1)

    def y(v):
        return pad_t + plot_h * (1 - v / y_max)

    def points(vals):
        return " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))

    weekday = "月火水木金土日"
    grid, ticks = [], []
    for frac in (0, 0.5, 1):
        gy = pad_t + plot_h * (1 - frac)
        grid.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l + plot_w}" y2="{gy:.1f}" '
                    f'stroke="var(--grid)" stroke-width="1"/>')
        ticks.append(f'<text x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end" '
                     f'class="tick">{int(y_max * frac)}</text>')
    labels = "".join(
        f'<text x="{x(i):.1f}" y="{h - 8}" text-anchor="middle" class="tick">'
        f'{weekday[i]} {d.month}/{d.day}</text>'
        for i, d in enumerate(days))
    dots = "".join(
        f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="8" fill="transparent">'
        f'<title>{days[i].month}/{days[i].day}: {v}人 (前週同曜日 {prev[i]}人)</title></circle>'
        f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3" fill="var(--series-1)"/>'
        for i, v in enumerate(cur))
    return f'''<svg viewBox="0 0 {w} {h}" role="img" aria-label="日別訪問者数: 対象週と前週の比較">
  {"".join(grid)}{"".join(ticks)}
  <polyline points="{points(prev)}" fill="none" stroke="var(--muted)"
    stroke-width="2" stroke-dasharray="5 4" stroke-linejoin="round"/>
  <polyline points="{points(cur)}" fill="none" stroke="var(--series-1)"
    stroke-width="2" stroke-linejoin="round"/>
  {dots}{labels}
  <text x="{x(len(days) - 1) + 10:.1f}" y="{y(cur[-1]) + 4:.1f}" class="series-label"
    fill="var(--series-1)">対象週</text>
  <text x="{x(len(days) - 1) + 10:.1f}" y="{y(prev[-1]) + 4:.1f}" class="series-label"
    fill="var(--muted)">前週</text>
</svg>'''


def bar_rows(rows: list, total: float, label_fn=None) -> str:
    out = []
    for r in rows:
        name = html.escape(str(label_fn(r) if label_fn else r["dimensions"][0]))
        v = r["metrics"][0]
        pct = v / total * 100 if total else 0
        out.append(
            f'<tr><td class="name">{name}</td>'
            f'<td class="num">{v:,}</td>'
            f'<td class="bar-cell"><div class="bar" style="width:{pct:.1f}%"></div>'
            f'<span class="pct">{pct:.1f}%</span></td></tr>')
    return "".join(out)


def build_html(site_id, wk_start, wk_end, cur, prev, pages, sources,
               countries, devices, chart_svg, insights) -> str:
    tiles = []
    tile_defs = [
        ("訪問者数", "visitors", lambda v: f"{v:,}", False),
        ("訪問数", "visits", lambda v: f"{v:,}", False),
        ("ページビュー", "pageviews", lambda v: f"{v:,}", False),
        ("直帰率", "bounce_rate", lambda v: f"{v:.0f}%", True),
        ("平均滞在時間", "visit_duration", fmt_duration, False),
    ]
    for label, key, fmt, lower_better in tile_defs:
        change = pct_change(cur[key], prev[key])
        tiles.append(
            f'<div class="tile"><div class="tile-label">{label}</div>'
            f'<div class="tile-value">{fmt(cur[key])}</div>'
            f'<div class="tile-delta {delta_class(change, lower_better)}">'
            f'{fmt_delta(change)} <span class="vs">前週比</span></div></div>')

    insight_items = "".join(f"<li>{html.escape(i)}</li>" for i in insights)
    country_rows = bar_rows(countries, cur["visitors"]) if countries else \
        '<tr><td colspan="3" class="empty">データなし</td></tr>'
    device_rows = bar_rows(devices, cur["visitors"]) if devices else \
        '<tr><td colspan="3" class="empty">データなし</td></tr>'

    return f'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Citadel AI ウェブ分析 週次レポート {wk_start.isoformat()}〜{wk_end.isoformat()}</title>
<style>
  :root {{
    color-scheme: light dark;
    --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e;
    --muted: #898781; --grid: #e1e0d9; --border: rgba(11,11,11,0.10);
    --series-1: #2a78d6; --bar: #86b6ef; --good: #006300; --bad: #d03b3b;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7;
      --muted: #898781; --grid: #2c2c2a; --border: rgba(255,255,255,0.10);
      --series-1: #3987e5; --bar: #1c5cab; --good: #0ca30c; --bad: #e66767;
    }}
  }}
  body {{ background: var(--page); color: var(--ink); margin: 0;
    font-family: system-ui, -apple-system, "Segoe UI", "Hiragino Sans", "Noto Sans JP", sans-serif;
    line-height: 1.6; padding: 2.5rem 1.25rem 4rem; }}
  main {{ max-width: 860px; margin: 0 auto; }}
  .eyebrow {{ font-size: .75rem; letter-spacing: .12em; text-transform: uppercase;
    color: var(--muted); font-weight: 600; }}
  h1 {{ font-size: 1.5rem; margin: .2rem 0 0; }}
  .period {{ color: var(--ink-2); margin: .3rem 0 1.8rem; }}
  h2 {{ font-size: 1.05rem; margin: 2.2rem 0 .8rem; }}
  .tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: .75rem; }}
  .tile {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
    padding: .9rem 1rem; }}
  .tile-label {{ font-size: .78rem; color: var(--ink-2); }}
  .tile-value {{ font-size: 1.55rem; font-weight: 650; margin: .1rem 0; }}
  .tile-delta {{ font-size: .82rem; font-weight: 600; }}
  .tile-delta .vs {{ color: var(--muted); font-weight: 400; }}
  .tile-delta.up {{ color: var(--good); }}
  .tile-delta.down {{ color: var(--bad); }}
  .tile-delta.flat {{ color: var(--muted); }}
  .panel {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
    padding: 1.1rem 1.25rem; overflow-x: auto; }}
  svg {{ width: 100%; height: auto; display: block; }}
  .tick {{ font-size: 11px; fill: var(--muted); font-variant-numeric: tabular-nums; }}
  .series-label {{ font-size: 12px; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
  td {{ padding: .45rem .5rem; border-top: 1px solid var(--grid); vertical-align: middle; }}
  tr:first-child td {{ border-top: none; }}
  td.name {{ max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; width: 5.5em; }}
  td.bar-cell {{ width: 40%; min-width: 140px; }}
  .bar {{ display: inline-block; height: 12px; background: var(--bar); border-radius: 3px;
    vertical-align: middle; }}
  .pct {{ font-size: .78rem; color: var(--muted); margin-left: .5em;
    font-variant-numeric: tabular-nums; }}
  .empty {{ color: var(--muted); }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
  @media (max-width: 640px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
  .insights li {{ margin: .4rem 0; }}
  footer {{ margin-top: 3rem; color: var(--muted); font-size: .8rem; }}
</style>
</head>
<body>
<main>
  <header>
    <p class="eyebrow">Citadel AI — {html.escape(site_id)} / Plausible Analytics</p>
    <h1>ウェブ分析 週次レポート</h1>
    <p class="period">対象期間: {wk_start.isoformat()} (月) 〜 {wk_end.isoformat()} (日) ・ 比較対象: 前週</p>
  </header>

  <div class="tiles">{"".join(tiles)}</div>

  <h2>日別訪問者数 (対象週 vs 前週)</h2>
  <div class="panel">{chart_svg}</div>

  <h2>上位ページ (訪問者数)</h2>
  <div class="panel"><table>
    {bar_rows(pages, cur["visitors"])}
  </table></div>

  <h2>流入元 (訪問者数)</h2>
  <div class="panel"><table>
    {bar_rows(sources, cur["visitors"])}
  </table></div>

  <div class="grid-2">
    <div><h2>国別</h2><div class="panel"><table>{country_rows}</table></div></div>
    <div><h2>デバイス</h2><div class="panel"><table>{device_rows}</table></div></div>
  </div>

  <h2>所見</h2>
  <div class="panel"><ul class="insights">{insight_items}</ul></div>

  <footer>Plausible Stats API から自動生成 ({dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")})</footer>
</main>
</body>
</html>
'''


def build_insights(cur, prev, pages, sources) -> list:
    insights = []
    v_change = pct_change(cur["visitors"], prev["visitors"])
    if v_change is not None:
        direction = "増加" if v_change >= 0 else "減少"
        insights.append(f"訪問者数は前週比 {abs(v_change):.1f}% の{direction}"
                        f" ({prev['visitors']:,}人 → {cur['visitors']:,}人)。")
    if pages:
        top = pages[0]
        share = top["metrics"][0] / cur["visitors"] * 100 if cur["visitors"] else 0
        insights.append(f"最も見られたページは {top['dimensions'][0]}"
                        f" (訪問者の {share:.1f}% が閲覧)。")
    if sources:
        top = sources[0]
        share = top["metrics"][0] / cur["visitors"] * 100 if cur["visitors"] else 0
        insights.append(f"最大の流入元は {top['dimensions'][0]} ({share:.1f}%)。")
    b_change = pct_change(cur["bounce_rate"], prev["bounce_rate"])
    if b_change is not None and abs(b_change) >= 5:
        trend = "改善" if b_change < 0 else "悪化"
        insights.append(f"直帰率が前週比 {abs(b_change):.1f}% {trend}"
                        f" ({prev['bounce_rate']:.0f}% → {cur['bounce_rate']:.0f}%)。")
    return insights or ["特筆すべき変化はありませんでした。"]


def build_markdown(site_id, wk_start, wk_end, cur, prev, pages, sources, insights) -> str:
    def row(label, key, fmt, lower_better=False):
        change = pct_change(cur[key], prev[key])
        return f"| {label} | {fmt(cur[key])} | {fmt(prev[key])} | {fmt_delta(change)} |"

    lines = [
        f"# Citadel AI ウェブ分析 週次レポート",
        "",
        f"**対象期間:** {wk_start.isoformat()} (月) 〜 {wk_end.isoformat()} (日) / サイト: {site_id}",
        "",
        "| 指標 | 今週 | 前週 | 前週比 |",
        "|---|---|---|---|",
        row("訪問者数", "visitors", lambda v: f"{v:,}"),
        row("訪問数", "visits", lambda v: f"{v:,}"),
        row("ページビュー", "pageviews", lambda v: f"{v:,}"),
        row("直帰率", "bounce_rate", lambda v: f"{v:.0f}%", True),
        row("平均滞在時間", "visit_duration", fmt_duration),
        "",
        "## 上位ページ",
        "",
    ]
    lines += [f"{i}. `{r['dimensions'][0]}` — {r['metrics'][0]:,}人"
              for i, r in enumerate(pages[:5], 1)] or ["データなし"]
    lines += ["", "## 流入元", ""]
    lines += [f"{i}. {r['dimensions'][0]} — {r['metrics'][0]:,}人"
              for i, r in enumerate(sources[:5], 1)] or ["データなし"]
    lines += ["", "## 所見", ""]
    lines += [f"- {i}" for i in insights]
    lines.append("")
    return "\n".join(lines)


def post_slack(cur, prev, wk_start, wk_end, insights):
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        print("SLACK_WEBHOOK_URL 未設定のため Slack 投稿をスキップ")
        return
    link = os.environ.get("REPORT_LINK", "").strip()
    v_change = pct_change(cur["visitors"], prev["visitors"])
    p_change = pct_change(cur["pageviews"], prev["pageviews"])
    text = "\n".join(filter(None, [
        f":bar_chart: *Citadel AI ウェブ分析 週次レポート* ({wk_start.isoformat()}〜{wk_end.isoformat()})",
        f"• 訪問者数: {cur['visitors']:,}人 ({fmt_delta(v_change)} 前週比)",
        f"• ページビュー: {cur['pageviews']:,} ({fmt_delta(p_change)} 前週比)",
        f"• 直帰率: {cur['bounce_rate']:.0f}% / 平均滞在: {fmt_duration(cur['visit_duration'])}",
        f"• {insights[0]}" if insights else None,
        f"詳細: {link}" if link else None,
    ]))
    req = urllib.request.Request(webhook, data=json.dumps({"text": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as res:
        print(f"Slack 投稿: HTTP {res.status}")


def main():
    if not os.environ.get("PLAUSIBLE_API_KEY"):
        sys.exit("エラー: 環境変数 PLAUSIBLE_API_KEY が設定されていません")

    today = dt.date.today()
    this_monday = today - dt.timedelta(days=today.weekday())
    wk_start = this_monday - dt.timedelta(days=7)
    wk_end = wk_start + dt.timedelta(days=6)
    prev_start, prev_end = wk_start - dt.timedelta(days=7), wk_start - dt.timedelta(days=1)
    days = [wk_start + dt.timedelta(days=i) for i in range(7)]

    site_id = resolve_site_id()
    print(f"site_id: {site_id} / 対象週: {wk_start} 〜 {wk_end}")

    cur = aggregate(site_id, wk_start, wk_end)
    prev = aggregate(site_id, prev_start, prev_end)
    pages = breakdown(site_id, "event:page", wk_start, wk_end, ("visitors", "pageviews"))
    sources = breakdown(site_id, "visit:source", wk_start, wk_end)
    countries = breakdown(site_id, "visit:country_name", wk_start, wk_end, limit=5)
    devices = breakdown(site_id, "visit:device", wk_start, wk_end, limit=5)
    series = daily_series(site_id, prev_start, wk_end)

    insights = build_insights(cur, prev, pages, sources)
    chart = build_chart_svg(days, series)
    html_report = build_html(site_id, wk_start, wk_end, cur, prev, pages, sources,
                             countries, devices, chart, insights)
    md_report = build_markdown(site_id, wk_start, wk_end, cur, prev, pages, sources, insights)

    os.makedirs(os.path.join(REPORTS_DIR, "history"), exist_ok=True)
    for path, content in [
        (os.path.join(REPORTS_DIR, "latest.html"), html_report),
        (os.path.join(REPORTS_DIR, "latest.md"), md_report),
        (os.path.join(REPORTS_DIR, "history", f"{wk_end.isoformat()}.html"), html_report),
    ]:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"生成: {os.path.relpath(path)}")

    post_slack(cur, prev, wk_start, wk_end, insights)


if __name__ == "__main__":
    main()
