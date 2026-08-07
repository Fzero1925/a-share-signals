# 组合级自动模拟盘 — 架构文档

## 1. 核心概念

**目标**：10万虚拟资金，按策略每日自动选股调仓，严格模拟A股交易规则，追踪账户净值，验证策略能否赚钱。

**与个股信号系统的区别**：

| | 个股信号系统（已有） | 组合模拟盘（本系统） |
|---|---|---|
| 输入 | 手动指定监控股票 | **全市场扫描自动选股** |
| 输出 | 每只股票独立买卖信号 | **整体账户：持仓/调仓/净值** |
| 资金 | 无资金概念 | **10万固定资金，等权分配** |
| 目的 | 看信号 | **验证策略长期能否赚钱** |

## 2. 系统流程（每日）

```
15:30 收盘后 CI 自动触发
  → screener: 全市场快照 → 按成交额过滤出300只活跃股
  → DataManager: 拉取300只历史K线（腾讯接口）
  → DailyMomentum: 计算动量/趋势/量能因子 → 打分 → 选Top 5
  → PortfolioEngine: 等权分配2万/只 → 调仓执行
      ├─ 卖出不在Top 5的持仓（T+1、跌停卖不出检查）
      └─ 买入新进Top 5的股票（涨停买不进检查、100股整手、手续费）
  → 记录净值 → 保存账户状态(signals/portfolio_state.json)
  → 生成 Pages 组合视图
```

## 3. 新增模块

### 3.1 `core/screener.py` — 全市场扫描器
- **东财** `push2.eastmoney.com/api/qt/clist/get`（主）：一次请求按成交额排序，分页取
- **新浪** `Market_Center.getHQNodeData`（备）：东财失败时自动回退
- 每接口 4 次重试 + 递增延迟（应对网络间歇失败）
- 过滤规则：
  - 成交额 ≥ 3亿（活跃度）
  - 剔除 ST/*ST
  - 剔除涨停（涨跌幅 ≥ 9.5%）和跌停（≤ -9.5%）
  - 取前 300 只

### 3.2 `core/portfolio_engine.py` — 组合引擎
```python
engine = PortfolioEngine(initial_capital=100000)
report = engine.execute_rebalance(
    date="2026-08-08",
    target_positions={"600519": 20000, ...},  # 目标持仓: 代码→金额
    prices={"600519": 1309.22, ...},          # 当前收盘价
    pre_closes={"600519": 1308.55, ...},      # 昨收（涨跌停判断用）
    names={"600519": "贵州茅台", ...},
)
```
- **T+1**：买入当日不能卖（`date > entry_date` 才可卖）
- **涨跌停**：`can_buy`（涨停买不进）/ `can_sell`（跌停卖不出），科创板/创业板 20% 阈值
- **100股整手**：`int(target / price / 100) * 100`
- **手续费**：佣金0.03%最低5元 + 过户费0.002% + 印花税0.1%（卖出）
- **等权分配**：`target = 初始资金 / top_n`
- 状态持久化：`signals/portfolio_state.json`（CI提交回仓库，跨运行保持持仓）

### 3.3 `strategies/daily_momentum.py` — 每日动量选股
5因子加权打分（百分位排名归一化）：

| 因子 | 权重 | 含义 |
|------|------|------|
| momentum_20d | 0.30 | 20日动量 |
| momentum_5d | 0.20 | 5日短期动量 |
| volume_ratio | 0.15 | 量比 |
| trend_strength | 0.20 | 距60日线位置 |
| rsi_score | 0.15 | RSI相对50偏离 |

- `score_universe(stock_data)` → 全池打分排序
- `select_top(stock_data, top_n)` → 选Top N（过滤低分 min_score=0.3）

### 3.4 `core/portfolio_backtest.py` — 组合回测器
- 输入：多股票历史数据 dict
- 逐日模拟：每日打分 → 次日调仓（严格T+1/涨跌停/手续费）
- 输出：净值曲线 + 交易记录 + 绩效（总收益/年化/回撤/夏普/胜率）
- **用途**：历史回测验证策略有效性（如：2025年至今跑出 +8.17%）

### 3.5 `ci/run_portfolio.py` — CI入口
```
python ci/run_portfolio.py
  → 输出 signals/portfolio.json（选股/调仓/绩效/持仓）+ portfolio_state.json（账户状态）
```

## 4. Pages 组合视图

`signals/portfolio.json` → 页面顶部卡片：
- 账户总览：总资产/总收益率/现金/持仓数/已平仓
- 今日选股表：Top N 股票、收盘价、目标金额
- 当前持仓表：名称/代码/股数/成本/现价/盈亏/买入日
- 调仓报告：卖出/买入/受阻笔数 + 受阻原因（涨停买不进等）
- 资金曲线：canvas 画布绘制近60日净值

## 5. 状态持久化设计

| 文件 | 内容 | 提交方式 |
|------|------|----------|
| `signals/portfolio_state.json` | 账户状态（现金/持仓/交易/净值历史） | CI 自动提交回仓库 |
| `signals/portfolio.json` | 当日报告（选股/调仓/绩效） | CI 自动提交 |
| `signals/latest.json` | 个股信号报告 | CI 自动提交 |

CI 每次全新 runner，但通过提交回仓库保持账户状态跨运行连续。

## 6. 运行时间

| Workflow | 时间 | 执行内容 |
|----------|------|----------|
| intraday.yml | 9:25/10:00/10:30/13:00/13:30/14:50 | 个股信号（不调仓） |
| daily.yml | 15:30/19:00 | **组合调仓** + 个股信号 + Pages部署 |

**注意**：组合调仓只在 15:30（收盘后）执行，盘中只更新个股信号不调仓。
