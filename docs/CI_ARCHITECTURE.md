# CI/CD 架构文档 — GitHub Actions 定时信号系统

## 1. 概述

利用 GitHub Actions 的定时任务能力，在 A 股交易时段自动运行策略引擎，生成买卖信号并推送到 GitHub Pages 展示。用户无需自建服务器。

**架构模式参考**：core-stock-daily-monitor（GitHub Actions + Pages 每日报告）的成熟模式。

## 2. 触发时间表（北京时间，仅工作日）

| 时段 | 触发时间 (BJT) | 对应UTC | cron表达式 | 用途 |
|------|---------------|---------|-----------|------|
| 盘前 | 09:00, 09:10, 09:20, 09:30 | 01:00, 01:10, 01:20, 01:30 | `0,10,20,30 1 * * 1-5` | 盘前数据与隔夜信息 |
| 上午盘中 | 10:00, 10:30, 11:00, 11:30 | 02:00, 02:30, 03:00, 03:30 | `0,30 2,3 * * 1-5` | 上午行情跟踪 |
| 下午盘中 | 13:00, 13:30, 14:00, 14:30 | 05:00, 05:30, 06:00, 06:30 | `0,30 5,6 * * 1-5` | 下午行情跟踪 |
| 尾盘 | 14:50 | 06:50 | `50 6 * * 1-5` | **关键窗口**：尾盘信号 |
| 收盘后 | 15:30 | 07:30 | `30 7 * * 1-5` | 完整日线确认 |
| 晚间 | 19:00 | 11:00 | `0 11 * * 1-5` | 复盘汇总 |

**注意**：GitHub Actions cron 使用 UTC 时间。北京时间 = UTC + 8 小时。

**实现说明**：
- 盘中高频（每30分钟）触发会导致信号频繁变化，建议将"盘中模式"与"日终模式"分开配置
- 每个 workflow 支持 `workflow_dispatch` 手动触发（用于补跑）

## 3. Workflow 设计

### 3.1 文件结构

```
.github/workflows/
├── intraday.yml       # 盘中信号（9:00-14:50 高频）
├── daily.yml          # 日终报告（15:30 + 19:00）
└── deploy-pages.yml   # Pages 部署（由上面两个调用或独立触发）
```

### 3.2 intraday.yml 模板

```yaml
name: A-share Intraday Signals

on:
  schedule:
    - cron: '0,10,20,30 1 * * 1-5'   # 09:00-09:30 BJT
    - cron: '0,30 2,3 * * 1-5'       # 10:00-11:30 BJT
    - cron: '0,30 5,6 * * 1-5'       # 13:00-14:30 BJT
    - cron: '50 6 * * 1-5'           # 14:50 BJT
  workflow_dispatch:

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: a-share-intraday
  cancel-in-progress: true

env:
  TZ: Asia/Shanghai

jobs:
  signals:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run strategy signals
        run: python ci/run_signals.py
        env:
          SIGNALS_FILE: signals/latest.json

      - name: Generate HTML report
        run: python ci/generate_report.py
        env:
          REPORT_DIR: public

      - name: Deploy to Pages
        uses: actions/configure-pages@v5

      - uses: actions/upload-pages-artifact@v3
        with:
          path: public

      - uses: actions/deploy-pages@v4
```

### 3.3 daily.yml 模板

```yaml
name: A-share Daily Report

on:
  schedule:
    - cron: '30 7 * * 1-5'   # 15:30 BJT
    - cron: '0 11 * * 1-5'   # 19:00 BJT
  workflow_dispatch:

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: a-share-daily
  cancel-in-progress: true

env:
  TZ: Asia/Shanghai

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt

      - name: Run daily report
        run: python ci/run_daily_report.py

      - name: Commit history
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add signals/ public/
          git commit -m "Daily report $(date +%Y-%m-%d)" || echo "No changes"
          git push origin main

      - name: Deploy to Pages
        uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: public
      - uses: actions/deploy-pages@v4
```

## 4. CI 脚本规范

### 4.1 `ci/run_signals.py` — 策略信号生成

**职责**：拉取数据 → 计算指标 → 跑策略 → 输出信号 JSON

```python
"""
用法: python ci/run_signals.py
读取: config/monitor_stocks.csv (监控股票池)
输出: signals/latest.json + signals/{YYYYMMDD}.json
"""
```

**输出 signals/latest.json 格式**：
```json
{
  "date": "2026-08-07",
  "generated_at": "2026-08-07 14:50:00",
  "strategy": "trend_follow",
  "signals": [
    {
      "code": "600519",
      "name": "贵州茅台",
      "action": "BUY",
      "price": 1780.0,
      "pct_change": 1.2,
      "reason": "EMA金叉+ADX>=25",
      "volume_ratio": 1.8,
      "suggested_position": 0.3
    }
  ],
  "market_summary": {
    "shanghai_index": 3200.5,
    "shanghai_pct": 0.85,
    "shenzhen_index": 10200.3,
    "shenzhen_pct": -0.32
  }
}
```

### 4.2 `ci/generate_report.py` — HTML 报告生成

**职责**：读取 signals JSON → 生成静态 HTML → 写入 public/

**输出结构**：
```
public/
├── index.html          # 今日信号首页（卡片式）
├── assets/
│   ├── style.css
│   └── app.js
├── history/
│   └── 2026-08-07.html # 历史信号归档
```

### 4.3 `ci/run_daily_report.py` — 日终报告

**职责**：
- 拉取全部监控股票日线
- 跑所有策略（4套）
- 生成多策略对比结果
- 写每日历史记录

## 5. 监控股票池配置

`config/monitor_stocks.csv`：
```csv
code,name
600519,贵州茅台
000001,平安银行
300750,宁德时代
601318,中国平安
```

## 6. GitHub Pages 配置

1. 仓库 Settings → Pages → Source: `GitHub Actions`（由 workflow 部署）
2. 公开仓库直接生效，无需额外认证
3. 首次部署后域名：`https://Fzero1925.github.io/a-share-signals/`

## 7. 错误处理与告警

| 场景 | 处理 |
|------|------|
| AKShare 请求失败 | 重试2次，仍失败则输出错误JSON + 保留旧数据 |
| 信号文件为空 | 生成"今日无信号"页面，不报错 |
| Workflow 失败 | GitHub Actions 会自动发邮件通知 |
| 数据延迟（未收盘） | 盘中模式使用最新可用数据，标注"盘中数据" |

## 8. 与本地系统的关系

| 组件 | 位置 | 用途 |
|------|------|------|
| core/ + strategies/ | 本地 + CI 共用 | 策略引擎（同一份代码） |
| ui/ + app.py | 仅本地 | Streamlit 深度分析 |
| ci/ | 仅 CI | 信号生成与报告 |
| signals/ + public/ | 仓库内 | CI 产出，供 Pages 和本地读取 |

**注意**：CI 中 `data/cache/` 不持久化（每次全新拉取），本地缓存仅用于本地加速。
