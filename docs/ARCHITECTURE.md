# 系统架构文档

## 1. 整体架构

### 1.1 双模式总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        双部署模式                                │
│                                                                  │
│  ┌────────────────────┐          ┌───────────────────────────┐  │
│  │ 本地 Streamlit      │          │ GitHub Actions + Pages    │  │
│  │ (深度交互分析)       │          │ (定时自动信号)             │  │
│  │                    │          │                           │  │
│  │ 数据浏览            │          │ 定时触发(交易日)           │  │
│  │ 策略回测            │  共用    │  → ci/run_signals.py      │  │
│  │ 模拟盘交易          │ ◄─────► │  → ci/generate_report.py  │  │
│  └────────────────────┘  引擎代码  │  → signals/*.json        │  │
│              ▲                    │  → public/*.html → Pages │  │
│              │                    └───────────────────────────┘  │
└──────────────┼───────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────┐
│                   核心引擎层 (本地+CI共用)                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐                │
│  │ DataMgr  │ │ Backtest │ │ PortfolioMgr     │                │
│  │ 数据管理  │ │ 回测引擎  │ │ 模拟账户管理      │                │
│  └──────────┘ └──────────┘ └──────────────────┘                │
│  ┌──────────────────────────────────────────────┐                │
│  │           Strategy Engine 策略引擎            │                │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌───────┐ │                │
│  │  │TrendFol│ │MeanRev │ │Momentum│ │MultiF │ │                │
│  │  │趋势跟踪│ │均值回归│ │动量突破│ │多因子 │ │                │
│  │  └────────┘ └────────┘ └────────┘ └───────┘ │                │
│  └──────────────────────────────────────────────┘                │
└──────────────────────┬───────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────┐
│                   数据层                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐                 │
│  │ AKShare  │ │ CSV Cache│ │  Indicators      │                 │
│  │ 在线获取  │ │ 本地缓存  │ │  技术指标计算     │                 │
│  └──────────┘ └──────────┘ └──────────────────┘                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 CI/CD 管线

```
GitHub Actions cron (UTC)         CI 产出                  GitHub Pages
───────────────┬─────────────     ────────────            ─────────────
09:00-14:50 盘中 │                 signals/latest.json  ──► public/index.html ──► 网页
15:30 收盘   ────┼──► run_signals ─► signals/20260807.json ─► public/history/   ──► 归档
19:00 晚间   ────┘     │                  │
                      │                  └─► git commit 回仓库（历史持久化）
                      └► generate_report ─► public/  → upload-pages-artifact → deploy-pages

详细规范见 docs/CI_ARCHITECTURE.md
```

## 2. 组件职责

### 2.1 DataManager (`core/data_manager.py`)
- 调用AKShare获取股票日线数据
- 本地CSV缓存，避免重复请求
- 返回标准化的pandas DataFrame
- 支持股票列表查询、代码标准化

### 2.2 Indicators (`core/indicators.py`)
- 纯函数，输入DataFrame，输出带指标的DataFrame
- 计算：MA, EMA, MACD(DIF/DEA/histogram), RSI, BOLL(upper/mid/lower), ADX, ATR, 成交量均线
- 不依赖策略，所有策略共用

### 2.3 StrategyEngine (`core/strategy_engine.py`)
- 策略基类定义接口
- 管理策略注册和运行
- 每个策略文件实现具体的信号生成逻辑

### 2.4 BacktestEngine (`core/backtest_engine.py`)
- 逐日模拟交易
- 处理T+1、涨跌停、手续费
- 输出：交易记录、权益曲线、绩效指标

### 2.5 PortfolioManager (`core/portfolio.py`)
- 虚拟账户：现金 + 持仓
- 记录每笔开平仓
- 计算浮动盈亏、已实现盈亏

### 2.6 UI Layer (`app.py` + `ui/`)
- Streamlit页面
- 每个页面一个文件
- 调用核心引擎层完成功能

## 3. 文件结构

```
stock/
├── app.py                       # Streamlit 入口，定义页面路由
├── requirements.txt             # Python依赖
├── docs/                        # 本文档目录（开发参考）
│   ├── PROJECT_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── STRATEGIES.md
│   ├── DATA_LAYER.md
│   ├── BACKTEST_ENGINE.md
│   ├── PAPER_TRADING.md
│   ├── UI_SPEC.md
│   ├── CI_ARCHITECTURE.md       # GitHub Actions 定时信号架构
│   └── IMPLEMENTATION_GUIDE.md
├── .github/
│   └── workflows/
│       ├── intraday.yml         # 盘中信号（高频定时）
│       └── daily.yml            # 日终报告（收盘+晚间）
├── core/                        # 核心引擎（本地+CI共用）
│   ├── __init__.py
│   ├── data_manager.py          # 数据获取与缓存
│   ├── indicators.py            # 技术指标计算
│   ├── strategy_base.py         # 策略基类
│   ├── strategy_engine.py       # 策略注册与运行器
│   ├── backtest_engine.py       # 回测引擎
│   └── portfolio.py             # 虚拟账户管理
├── strategies/                  # 具体策略实现
│   ├── __init__.py
│   ├── trend_follow.py          # 趋势跟踪（EMA双均线+ADX过滤）
│   ├── mean_revert.py           # 均值回归（布林带+RSI）
│   ├── momentum.py              # 动量突破（新高+放量）
│   └── multi_factor.py          # 多因子打分轮动
├── ci/                          # CI专用脚本（GitHub Actions运行）
│   ├── run_signals.py           # 拉数据→跑策略→输出signals/*.json
│   └── generate_report.py       # JSON→HTML报告→public/
├── ui/                          # 界面页面（仅本地）
│   ├── __init__.py
│   ├── page_data.py             # 数据浏览页
│   ├── page_backtest.py         # 回测页
│   └── page_paper_trading.py    # 模拟盘页
├── config/
│   ├── settings.py              # 全局配置常量
│   └── monitor_stocks.csv       # CI监控股票池
├── signals/                     # CI产出信号JSON
│   ├── latest.json              # 最新信号
│   └── {YYYYMMDD}.json          # 历史信号
├── public/                      # GitHub Pages站点（CI生成）
│   ├── index.html
│   ├── assets/
│   └── history/
├── data/                        # 本地缓存（CI不持久化）
│   ├── cache/
│   └── portfolio/
└── test_integration.py          # 端到端集成测试
```

## 4. 数据流

### 4.1 回测流程
```
用户选择股票+策略+日期范围
  → DataManager 拉取K线数据（优先缓存）
  → Indicators 计算技术指标
  → Strategy 读取指标DataFrame，生成信号列（1=buy, -1=sell, 0=hold）
  → BacktestEngine 逐行遍历，信号触发时模拟交易
  → 计算绩效指标
  → UI展示K线图(带信号标记) + 资金曲线 + 统计表
```

### 4.2 模拟盘流程
```
用户选择策略+股票池
  → DataManager 拉取最新K线数据
  → Indicators 计算技术指标
  → Strategy 生成最新交易日的信号
  → PortfolioManager 根据信号更新持仓
  → UI展示信号列表 + 当前持仓 + 历史盈亏
```

## 5. 关键数据结构

### 5.1 K线数据 DataFrame 列
```
date        datetime64    日期
open        float64       开盘价
high        float64       最高价
low         float64       最低价
close       float64       收盘价
volume      float64       成交量（手）
amount      float64       成交额（元）
```

### 5.2 信号 DataFrame（在K线基础上增加）
```
signal      int8          交易信号: 1=买入, -1=卖出, 0=无信号
position    int8          持仓状态: 1=持有多头, 0=空仓
```

### 5.3 交易记录
```python
{
    "date": "2024-01-15",
    "action": "BUY" | "SELL",
    "price": 10.50,
    "shares": 1000,
    "cost": 31.50,           # 手续费
    "reason": "EMA金叉"       # 触发原因
}
```

### 5.4 绩效指标
```python
{
    "total_return": 0.25,      # 总收益率 25%
    "annual_return": 0.12,     # 年化收益率
    "max_drawdown": -0.15,     # 最大回撤
    "sharpe_ratio": 1.5,       # 夏普比率（无风险利率按2%）
    "win_rate": 0.45,          # 胜率
    "profit_loss_ratio": 2.1,  # 盈亏比
    "total_trades": 50,        # 总交易次数
}
```
