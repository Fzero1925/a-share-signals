import html
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import PUBLIC_DIR, SIGNALS_DIR

ACTION_STYLE = {
    "BUY": "background:#2e7d32;color:#fff;",
    "SELL": "background:#c62828;color:#fff;",
    "HOLD": "background:#546e7a;color:#fff;",
}

ACTION_LABEL = {"BUY": "买入", "SELL": "卖出", "HOLD": "观望"}


def build_html(data: dict, page_title: str = None, extra_html: str = "", is_history: bool = False) -> str:
    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    generated = data.get("generated_at", "")
    title = page_title or f"A股信号 {date}"

    nav_html = ""
    if is_history:
        nav_html = (
            '<div style="margin-bottom:16px;">'
            '<a href="../index.html" style="display:inline-block;padding:8px 18px;'
            'background:#2196f3;color:#fff;border-radius:6px;text-decoration:none;'
            'font-size:14px;">← 返回今日信号</a></div>'
        )

    summary_html = ""
    market = data.get("market_summary", {})
    for key, label in [("shanghai", "上证指数"), ("shenzhen", "深证成指")]:
        if key in market:
            idx = market[key]
            color = "red" if idx["pct_change"] >= 0 else "green"
            summary_html += (
                f'<div class="index"><span class="idx-label">{label}</span>'
                f'<span class="idx-value">{idx["close"]:.2f}</span>'
                f'<span style="color:{color}">{idx["pct_change"]:+.2f}%</span></div>'
            )

    cards = ""
    for sig in data.get("signals", []):
        code = html.escape(str(sig.get("code", "")))
        name = html.escape(str(sig.get("name", code)))
        strategies_html = ""
        for s in sig.get("strategies", []):
            s_name = s.get("strategy", "")
            action = s.get("action", "HOLD")
            reason = html.escape(s.get("reason", ""))
            close = s.get("close")
            pct = s.get("pct_change")
            rsi = s.get("rsi14")
            adx = s.get("adx14")
            pct_str = f"{pct:+.2f}%" if pct is not None else "-"
            pct_color = "red" if pct is not None and pct >= 0 else "green"
            rsi_str = f"{rsi:.1f}" if rsi is not None else "-"
            adx_str = f"{adx:.1f}" if adx is not None else "-"
            strategies_html += (
                f'<tr><td>{html.escape(s_name)}</td>'
                f'<td><span class="badge" style="{ACTION_STYLE.get(action, ACTION_STYLE["HOLD"])}">'
                f'{ACTION_LABEL.get(action, action)}</span></td>'
                f'<td>{close if close else "-"}</td>'
                f'<td style="color:{pct_color}">{pct_str}</td>'
                f'<td>{rsi_str}</td><td>{adx_str}</td><td>{reason}</td></tr>'
            )
        if not strategies_html:
            strategies_html = '<tr><td colspan="7">暂无信号</td></tr>'
        cards += (
            f'<div class="card"><div class="card-header"><span class="stock-name">{name}</span>'
            f'<span class="stock-code">{code}</span></div>'
            f'<table><thead><tr><th>策略</th><th>信号</th><th>收盘</th><th>涨跌</th>'
            f'<th>RSI</th><th>ADX</th><th>原因</th></tr></thead><tbody>{strategies_html}</tbody></table>'
            f"</div>"
        )

    if not cards:
        cards = '<div class="card"><p class="empty">今日无信号</p></div>'

    failures_html = ""
    if data.get("failures"):
        fails = "<br>".join(
            f"{html.escape(str(f.get('code', '')))} {html.escape(str(f.get('name', '')))}: {html.escape(str(f.get('error', '')))}"
            for f in data["failures"]
        )
        failures_html = f'<div class="notice">⚠️ {len(data["failures"])} 只股票获取失败:<br>{fails}</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,"Microsoft YaHei",sans-serif; background:#f5f6fa; color:#333; padding:20px; }}
.container {{ max-width:960px; margin:0 auto; }}
h1 {{ font-size:24px; margin-bottom:8px; }}
.sub {{ color:#888; font-size:13px; margin-bottom:20px; }}
.indexes {{ display:flex; gap:16px; margin-bottom:20px; }}
.index {{ background:#fff; padding:12px 20px; border-radius:8px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
.idx-label {{ display:block; color:#888; font-size:12px; }}
.idx-value {{ font-size:20px; font-weight:600; margin-right:8px; }}
.card {{ background:#fff; border-radius:10px; box-shadow:0 2px 6px rgba(0,0,0,.06); margin-bottom:16px; overflow:hidden; }}
.card-header {{ display:flex; justify-content:space-between; align-items:center; padding:14px 20px; border-bottom:1px solid #eee; }}
.stock-name {{ font-size:17px; font-weight:600; }}
.stock-code {{ color:#999; font-size:13px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th {{ text-align:left; background:#fafafa; padding:10px 20px; color:#666; font-weight:500; }}
td {{ padding:10px 20px; border-top:1px solid #f0f0f0; }}
.badge {{ display:inline-block; padding:3px 10px; border-radius:12px; font-size:13px; }}
.notice {{ background:#fff3cd; border:1px solid #ffe69c; border-radius:8px; padding:12px 16px; margin-bottom:16px; font-size:14px; }}
.empty {{ text-align:center; padding:30px; color:#999; }}
@media (max-width:600px) {{
  body {{ padding:12px; }}
  .indexes {{ flex-direction:column; gap:8px; }}
  td, th {{ padding:8px 12px; font-size:12px; }}
}}
</style>
</head>
<body>
<div class="container">
{nav_html}
<h1>📈 A股策略信号 {html.escape(date)}</h1>
<div class="sub">生成时间: {html.escape(generated)}</div>
<div class="indexes">{summary_html}</div>
{extra_html}
{failures_html}
{cards}
<div class="sub" style="margin-top:24px;text-align:center">数据来源: 腾讯行情 | 仅供学习研究，不构成投资建议</div>
</div>
</body>
</html>"""


def build_portfolio_html(portfolio_path: str) -> str:
    if not os.path.exists(portfolio_path):
        return ""
    with open(portfolio_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    perf = data.get("performance", {})
    total_return = perf.get("total_return", 0)
    color = "red" if total_return >= 0 else "green"

    stats = f"""
    <div class="indexes">
      <div class="index"><span class="idx-label">总资产</span><span class="idx-value">{perf.get('total_equity', 0):,.0f}</span></div>
      <div class="index"><span class="idx-label">总收益率</span><span class="idx-value" style="color:{color}">{total_return:+.2%}</span></div>
      <div class="index"><span class="idx-label">现金</span><span class="idx-value">{perf.get('cash', 0):,.0f}</span></div>
      <div class="index"><span class="idx-label">持仓数</span><span class="idx-value">{perf.get('positions', 0)}</span></div>
      <div class="index"><span class="idx-label">已平仓</span><span class="idx-value">{perf.get('total_trades', 0)}</span></div>
    </div>
    """

    positions_html = ""
    for pos in data.get("positions", []):
        code = html.escape(str(pos.get("code", "")))
        name = html.escape(str(pos.get("name", code)))
        price = pos.get("current_price", pos.get("entry_price", 0))
        entry = pos.get("entry_price", 0)
        pnl = (price - entry) * pos.get("shares", 0)
        pnl_color = "red" if pnl >= 0 else "green"
        positions_html += (
            f'<tr><td>{name}</td><td>{code}</td><td>{pos.get("shares", 0)}</td>'
            f'<td>{entry:.2f}</td><td>{price:.2f}</td>'
            f'<td style="color:{pnl_color}">{pnl:+.2f}</td>'
            f'<td>{html.escape(str(pos.get("entry_date", "")))}</td></tr>'
        )
    if not positions_html:
        positions_html = '<tr><td colspan="7" class="empty">当前空仓</td></tr>'

    selected_html = ""
    for sel in data.get("selected", []):
        selected_html += (
            f'<tr><td>{html.escape(str(sel.get("name", sel.get("code", ""))))}</td>'
            f'<td>{html.escape(str(sel.get("code", "")))}</td>'
            f'<td>{sel.get("close", 0):.2f}</td><td>{sel.get("target_amount", 0):,.0f}</td></tr>'
        )
    if not selected_html:
        selected_html = '<tr><td colspan="4" class="empty">今日无选股</td></tr>'

    report = data.get("rebalance", {})
    blocked_html = ""
    for b in report.get("blocked", []):
        blocked_html += f'<li>{html.escape(str(b.get("code", "")))}: {html.escape(str(b.get("reason", "")))}</li>'

    equity_html = ""
    eq = data.get("equity_history", [])
    if eq:
        points = ",".join(
            f'{{"d":"{html.escape(str(e.get("date", "")))}","v":{e.get("equity", 0)}}}' for e in eq[-60:]
        )
        equity_html = (
            f'<canvas id="eqChart" height="80"></canvas>'
            f'<script>const eq=JSON.parse(\'[{points}]\');'
            f'const cv=document.getElementById("eqChart").getContext("2d");'
            f'cv.fillStyle="#fafafa";cv.fillRect(0,0,cv.canvas.width,cv.canvas.height);'
            f'const mn=Math.min(...eq.map(p=>p.v)),mx=Math.max(...eq.map(p=>p.v));'
            f'const w=cv.canvas.width,h=cv.canvas.height;'
            f'cv.strokeStyle="#2196f3";cv.lineWidth=2;cv.beginPath();'
            f'eq.forEach((p,i)=>{{const x=i/(eq.length-1||1)*w,y=h-10-((p.v-mn)/((mx-mn)||1))*(h-30);'
            f'i?cv.lineTo(x,y):cv.moveTo(x,y);}});cv.stroke();</script>'
        )

    return f"""
    <div class="card">
      <div class="card-header"><span class="stock-name">💼 模拟盘组合账户</span>
      <span class="stock-code">{html.escape(data.get('strategy', ''))}</span></div>
      <div style="padding:16px 20px;">
      {stats}
      {equity_html}
      <h3 style="font-size:15px;margin:12px 0 6px;">今日选股 (Top {len(data.get('selected', []))})</h3>
      <table><thead><tr><th>名称</th><th>代码</th><th>收盘</th><th>目标金额</th></tr></thead>
      <tbody>{selected_html}</tbody></table>
      <h3 style="font-size:15px;margin:12px 0 6px;">当前持仓</h3>
      <table><thead><tr><th>名称</th><th>代码</th><th>股数</th><th>成本</th><th>现价</th><th>盈亏</th><th>买入日</th></tr></thead>
      <tbody>{positions_html}</tbody></table>
      <h3 style="font-size:15px;margin:12px 0 6px;">调仓报告</h3>
      <p style="font-size:13px;color:#666;">卖出 {len(report.get('sold', []))} 笔，买入 {len(report.get('bought', []))} 笔，受阻 {len(report.get('blocked', []))} 笔</p>
      {f'<ul style="font-size:13px;color:#c62828;">{blocked_html}</ul>' if blocked_html else ''}
      </div>
    </div>
    """


def build_history_list(history_dir: str) -> str:
    if not os.path.isdir(history_dir):
        return ""
    files = sorted(
        [f for f in os.listdir(history_dir) if f.endswith(".html")],
        reverse=True,
    )
    if not files:
        return ""
    items = "".join(f'<li><a href="history/{html.escape(f)}">{html.escape(f.replace(".html", ""))}</a></li>' for f in files[:30])
    return (
        f'<h2 style="font-size:18px;margin:24px 0 10px;">历史信号</h2>'
        f'<ul style="list-style:none">{items}</ul>'
        f'<p style="font-size:12px;color:#999;margin-top:6px;">'
        f'共 {len(files)} 天记录，全部永久保存在仓库（GitHub Actions 每日自动归档）</p>'
    )


def main() -> int:
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    os.makedirs(os.path.join(PUBLIC_DIR, "history"), exist_ok=True)

    latest_path = os.path.join(SIGNALS_DIR, "latest.json")
    if not os.path.exists(latest_path):
        print("未找到 signals/latest.json，请先运行 run_signals.py", file=sys.stderr)
        return 1

    with open(latest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))

    portfolio_html = build_portfolio_html(os.path.join(SIGNALS_DIR, "portfolio.json"))

    index_html = build_html(data, extra_html=portfolio_html)
    index_html = index_html.replace("</body>", build_history_list(os.path.join(PUBLIC_DIR, "history")) + "</body>")
    with open(os.path.join(PUBLIC_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    history_path = os.path.join(PUBLIC_DIR, "history", f"{date.replace('-', '')}.html")
    with open(history_path, "w", encoding="utf-8") as f:
        f.write(build_html(data, extra_html=portfolio_html, is_history=True))

    print(f"报告已生成: {os.path.join(PUBLIC_DIR, 'index.html')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
