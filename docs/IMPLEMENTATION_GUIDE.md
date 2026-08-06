# 实现指南 — 给AI开发者的精确指令

## 重要：阅读顺序

**必须按本文档顺序实现，禁止跳步。** 每完成一步，验证通过后再进入下一步。

---

## 第0步：环境搭建

### 创建文件 `requirements.txt`

```
streamlit>=1.28.0
akshare>=1.12.0
pandas>=2.0.0
numpy>=1.24.0
plotly>=5.15.0
pandas-ta>=0.3.14b0
```

安装命令：`pip install -r requirements.txt`

### 创建 `config/settings.py`

```python
# 全局配置常量
INITIAL_CAPITAL = 100000.0
STAMP_TAX = 0.001
COMMISSION = 0.0003
MIN_COMMISSION = 5.0
TRANSFER_FEE = 0.00002
CACHE_DIR = "data/cache"
PORTFOLIO_DIR = "data/portfolio"
RISK_FREE_RATE = 0.02
LIMIT_UP_PCT_MAIN = 0.10
LIMIT_UP_PCT_GEM = 0.20
```

### 创建空目录结构

确保以下目录存在（`__init__.py` 可以为空）：
- `core/` + `core/__init__.py`
- `strategies/` + `strategies/__init__.py`
- `ui/` + `ui/__init__.py`
- `data/cache/daily/`
- `data/portfolio/`

**验证**：`python -c "import streamlit; import akshare; import pandas; import plotly; print('OK')"` 无报错。

---

## 第1步：数据层 (`core/data_manager.py`)

### 必须实现的类和方法

```python
class DataFetchError(Exception):
    pass

class DataManager:
    def __init__(self, cache_dir: str = "data/cache"):
        pass

    def get_daily(self, stock_code: str, start_date: str = "20150101",
                  end_date: str = None, use_cache: bool = True) -> pd.DataFrame:
        pass

    def get_stock_list(self) -> pd.DataFrame:
        pass

    def standardize_code(self, code: str) -> str:
        pass
```

### 实现细节

**`standardize_code(code)`**：
- 移除所有非数字字符
- 如果长度<6，左侧补0到6位
- 返回6位字符串

**`get_daily(stock_code, start_date, end_date, use_cache)`**：
- `end_date=None` 时使用 `datetime.now().strftime("%Y%m%d")`
- 缓存文件路径：`{cache_dir}/daily/{stock_code}.csv`
- 缓存逻辑按 DATA_LAYER.md 第2.2节实现
- AKShare调用：`ak.stock_zh_a_hist(symbol=stock_code, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")`
- 列名映射（必须严格按此顺序返回）：
  ```python
  column_map = {
      '日期': 'date', '开盘': 'open', '最高': 'high',
      '最低': 'low', '收盘': 'close', '成交量': 'volume', '成交额': 'amount'
  }
  ```
- 只保留映射后的列
- `date` 转为 datetime64 类型
- 按 date 升序排列
- 网络请求加 try/except，失败 raise DataFetchError

**`get_stock_list()`**：
- 调用 `ak.stock_zh_a_spot_em()`
- 返回列：`['code', 'name', 'price', 'pct_change', 'volume', 'amount', 'pe']`（code为6位字符串）

**验证**：
```python
dm = DataManager()
df = dm.get_daily('000001', '20240101', '20240131')
assert len(df) > 0
assert list(df.columns) == ['date', 'open', 'high', 'low', 'close', 'volume', 'amount']
```

---

## 第2步：技术指标 (`core/indicators.py`)

### 必须实现的函数

```python
def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    输入: 包含OHLCV的DataFrame
    输出: 原DataFrame增加以下列:
      ma5, ma10, ma20, ma60
      ema5, ema10, ema20
      macd_dif, macd_dea, macd_hist
      rsi14
      boll_upper, boll_mid, boll_lower
      adx14
      atr14
      vol_ma5, vol_ma20
      high_20, low_10
    """
```

### 实现细节

使用 **pandas-ta** 库：

```python
import pandas_ta as ta

def add_all_indicators(df):
    # 均线
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    
    # EMA
    df['ema5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    
    # MACD
    macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
    df['macd_dif'] = macd['MACD_12_26_9']
    df['macd_dea'] = macd['MACDs_12_26_9']
    df['macd_hist'] = macd['MACDh_12_26_9']
    
    # RSI
    df['rsi14'] = ta.rsi(df['close'], length=14)
    
    # BOLL
    boll = ta.bbands(df['close'], length=20, std=2)
    df['boll_upper'] = boll['BBU_20_2.0']
    df['boll_mid'] = boll['BBM_20_2.0']
    df['boll_lower'] = boll['BBL_20_2.0']
    
    # ADX
    adx = ta.adx(df['high'], df['low'], df['close'], length=14)
    df['adx14'] = adx['ADX_14']
    
    # ATR
    df['atr14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    # 成交量均线
    df['vol_ma5'] = df['volume'].rolling(5).mean()
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    
    # N日最高最低
    df['high_20'] = df['close'].rolling(20).max()
    df['low_10'] = df['close'].rolling(10).min()
    
    return df
```

**注意**：
- 不修改原有列
- 前N行的NaN值是正常的（rolling window不足）
- 不要用 `fillna` 填充——策略中自然会处理NaN

**验证**：
```python
dm = DataManager()
df = dm.get_daily('000001', '20240101', '20240630')
df = add_all_indicators(df)
assert 'ma20' in df.columns
assert 'rsi14' in df.columns
assert 'boll_mid' in df.columns
```

---

## 第3步：策略实现 (`strategies/`)

### 3.1 策略基类 (`core/strategy_base.py`)

```python
from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    def __init__(self, params: dict = None):
        self.params = params if params else self.get_default_params()
        self.name = self.__class__.__name__

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        输入: 含OHLCV+技术指标的DataFrame
        输出: 原DataFrame增加两列:
          - signal: int, 1=买入(开仓), -1=卖出(平仓), 0=无操作
          - position: int, 1=建议持仓, 0=建议空仓
        """
        pass

    @staticmethod
    @abstractmethod
    def get_default_params() -> dict:
        pass
```

### 3.2 趋势跟踪策略 (`strategies/trend_follow.py`)

**类名**：`TrendFollowStrategy(BaseStrategy)`

**默认参数**：
```python
{
    'fast_ema': 5,
    'slow_ema': 20,
    'adx_period': 14,
    'adx_threshold': 25,
    'stop_loss_pct': 0.05,
    'trailing_stop_pct': 0.03,
    'take_profit_pct': 0.15,
}
```

**`generate_signals(df)` 实现逻辑**：
1. 确保df包含 `ema5`, `ema20`, `adx14` 列（如果不存在，先计算）
2. 初始化 `signal` 列全为0，`position` 列全为0
3. 遍历df的每一行（从第max(fast_ema, slow_ema, adx_period)行开始）：
   - **进场条件（买入信号=1）**：
     - `ema5[t] > ema20[t]` AND `ema5[t-1] <= ema20[t-1]`（金叉日）
     - `adx14[t] >= adx_threshold`
     - `close[t] > ema20[t]`
     - `position[t-1] == 0`（当前无持仓）
   - **出场条件（卖出信号=-1）**：
     - 条件A：`ema5[t] < ema20[t]`（死叉）
     - 条件B：`close[t] <= entry_price * (1 - stop_loss_pct)`
     - 条件C：`close[t] <= highest_since_entry * (1 - trailing_stop_pct)`
     - 条件D：`close[t] >= entry_price * (1 + take_profit_pct)`
     - 任一满足 AND `position[t-1] == 1`
   - 更新 `position[t]`：有买入=1，有卖出=0，否则继承 `position[t-1]`
   - 维护 `entry_price` 和 `highest_since_entry` 变量（在持仓期间更新）

### 3.3 均值回归策略 (`strategies/mean_revert.py`)

**类名**：`MeanRevertStrategy(BaseStrategy)`

**默认参数**：
```python
{
    'bb_period': 20,
    'bb_std': 2.0,
    'rsi_period': 14,
    'rsi_oversold': 35,
    'rsi_overbought': 65,
    'stop_loss_pct': 0.03,
    'take_profit_pct': 0.05,
    'max_hold_days': 7,
}
```

**`generate_signals(df)` 实现逻辑**：
1. 确保df包含 `boll_upper`, `boll_mid`, `boll_lower`, `rsi14` 列
2. 计算 `bb_width = (boll_upper - boll_lower) / boll_mid`
3. 遍历每一行：
   - **买入条件**：
     - `close[t] <= boll_lower[t] * 1.01`
     - `rsi14[t] < rsi_oversold`
     - `bb_width[t] > 0.05`
     - `close[t] > close[t-1]`（收阳确认）
     - `position[t-1] == 0`
   - **卖出条件**：
     - `close[t] >= boll_mid[t]`（回归中轨）
     - OR `rsi14[t] > rsi_overbought`
     - OR 持仓天数 >= max_hold_days
     - OR 止损/止盈触发
   - 维护 `hold_days` 计数器

### 3.4 动量突破策略 (`strategies/momentum.py`)

**类名**：`MomentumStrategy(BaseStrategy)`

**默认参数**：
```python
{
    'lookback_high': 20,
    'lookback_low': 10,
    'volume_ma': 20,
    'volume_ratio': 1.5,
    'stop_loss_pct': 0.05,
    'trailing_stop_pct': 0.04,
}
```

**`generate_signals(df)` 实现逻辑**：
1. 确保df包含 `high_20`, `low_10`, `vol_ma20`, `ma60` 列
2. 计算 `vol_ratio = volume / vol_ma20`
3. 遍历每一行：
   - **买入条件**：
     - `close[t] > high_20[t-1]`（突破前20日最高收盘价）
     - `vol_ratio[t] >= volume_ratio`（放量确认）
     - `close[t] > ma60[t]`（中期趋势向上）
     - `position[t-1] == 0`
   - **卖出条件**：
     - `close[t] < ma10[t]`（跌破10日线）
     - OR `close[t] <= low_10[t-1]`
     - OR 止损/移动止损触发

### 3.5 多因子打分策略 (`strategies/multi_factor.py`)

**类名**：`MultiFactorStrategy(BaseStrategy)`

**默认参数**：
```python
{
    'top_n': 5,
    'momentum_period': 20,
    'volume_period': 5,
    'rebalance_freq': 'weekly',  # 'weekly' or 'monthly'
}
```

**`generate_signals(df)` 实现逻辑**（需多只股票数据）：
- 此策略特殊：接收一个 `dict[str, pd.DataFrame]`（股票池）
- 对每只股票计算5个因子得分
- 按百分位排名归一化
- 加权求和，取top N
- 在调仓日生成信号：卖出跌出top N的，买入新进top N的

**因子计算**（每只股票单独计算）：
```python
momentum_20d = (close / close.shift(20) - 1).iloc[-1]
volatility_20d = -1 * returns.rolling(20).std().iloc[-1]  # 取负，波动小加分
volume_ratio_5d = (volume / volume.shift(5).mean()).iloc[-1]
trend_strength = (close - ma60) / ma60
rsi_score = (rsi14 - 50) / 50
```

---

## 第4步：回测引擎 (`core/backtest_engine.py`)

### 必须实现的类

```python
class BacktestEngine:
    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital

    def run(self, df: pd.DataFrame, stock_code: str = "000001",
            position_pct: float = 0.3) -> dict:
        pass

    @staticmethod
    def calc_metrics(equity_curve: pd.DataFrame, trades: list,
                     initial_capital: float) -> dict:
        pass
```

### `run()` 实现细节

严格按照 BACKTEST_ENGINE.md 第4节的伪代码实现。关键点：

1. **T+1检查**：`holding_shares > 0 AND date > entry_date` 才允许卖出（即买入日当天不能卖）
2. **涨跌停检查**：用 `can_buy()` / `can_sell()` 函数
3. **仓位计算**：
   ```python
   buy_amount = cash * position_pct          # 使用可用现金 * 仓位比例
   shares = int(buy_amount / close / 100) * 100
   ```
4. **手续费计算**：使用 `calc_cost()` 函数
5. **返回数据结构**：
   ```python
   {
       'trades': pd.DataFrame,      # 列: date, action, price, shares, cost, pnl, pnl_pct, reason
       'equity_curve': pd.DataFrame, # 列: date, equity, cash, position_value, drawdown
       'metrics': dict,              # 见下方 calc_metrics
   }
   ```
6. **pnl 和 pnl_pct 只在卖出时计算**：对比卖出价和买入价，扣除双向手续费

### `calc_metrics()` 实现细节

严格按照 BACKTEST_ENGINE.md 第5节的公式实现。注意：
- `drawdown` 用 `(equity - cummax) / cummax` 计算
- 夏普比率分母可能为0，需处理 `if excess.std() > 0 else 0`
- `win_rate` = 盈利交易数 / 总交易对数（一次买卖为一对）
- `profit_loss_ratio` = 平均盈利% / |平均亏损%|

### 验证
```python
dm = DataManager()
df = dm.get_daily('000001', '20200101', '20241231')
from core.indicators import add_all_indicators
df = add_all_indicators(df)
from strategies.trend_follow import TrendFollowStrategy
strat = TrendFollowStrategy()
df = strat.generate_signals(df)
engine = BacktestEngine(100000)
result = engine.run(df, '000001')
assert 'trades' in result
assert 'metrics' in result
print(result['metrics'])
```

---

## 第5步：模拟盘管理 (`core/portfolio.py`)

### 必须实现的类

```python
class PortfolioManager:
    def __init__(self, initial_capital: float = 100000.0):
        pass

    def buy(self, stock_code: str, price: float, shares: int,
            date: str, reason: str = "") -> bool:
        pass

    def sell(self, stock_code: str, price: float, date: str,
             reason: str = "") -> bool:
        pass

    def get_position(self, stock_code: str) -> dict:
        pass

    def get_all_positions(self) -> dict:
        pass

    def get_total_equity(self, current_prices: dict) -> float:
        pass

    def save_state(self, filepath: str = None):
        pass

    def load_state(self, filepath: str = None):
        pass
```

实现细节见 PAPER_TRADING.md。默认持久化路径：`data/portfolio/paper_account.json`。

---

## 第6步：UI 页面

### 6.1 入口文件 `app.py`

```python
import streamlit as st

st.set_page_config(
    page_title="A股模拟盘回测系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("A股模拟盘回测系统")
page = st.sidebar.radio(
    "导航",
    ["📊 数据浏览", "📈 策略回测", "💰 模拟盘交易"],
)

if page == "📊 数据浏览":
    from ui.page_data import show
elif page == "📈 策略回测":
    from ui.page_backtest import show
elif page == "💰 模拟盘交易":
    from ui.page_paper_trading import show

show()
```

### 6.2 数据浏览页 (`ui/page_data.py`)

- 顶部：股票代码输入框 + 搜索按钮
- 日期范围选择器（双日期输入框）
- "获取数据" 按钮
- 点击后：显示K线图（Plotly candlestick + 成交量副图）
- K线图下方：技术指标叠加选项（checkbox多选：MA5/MA10/MA20/EMA/BOLL）
- 底部：技术指标数值面板（最新日的MA、RSI、MACD、ADX值）

### 6.3 策略回测页 (`ui/page_backtest.py`)

- 左侧/顶部：策略选择下拉、股票代码输入、日期范围、初始资金
- 可折叠的参数面板（`st.expander`），每个策略参数用 `st.slider` 或 `st.number_input`
- "运行回测" 按钮
- 点击后：
  1. 显示 K线图 + 买卖标记（买入绿三角在K线下方，卖出红三角在K线上方）
  2. 显示资金曲线（策略权益 vs 买入持有基准，双线图）
  3. 显示回撤曲线
  4. 显示绩效卡片（`st.metric` 横向排列）：总收益、年化收益、最大回撤、夏普比率、胜率、盈亏比、交易次数
  5. 显示交易明细表（`st.dataframe`）

### 6.4 模拟盘交易页 (`ui/page_paper_trading.py`)

- 账户概览卡片行（`st.metric`）：总资产、现金、持仓市值、总收益率
- 策略选择 + 股票池输入（逗号分隔的代码列表）
- "生成今日信号" 按钮
- 信号推荐表格（`st.dataframe`）：代码、名称、信号类型(BUY/SELL/HOLD)、现价、建议股数、触发原因
- 当前持仓表格：代码、股数、成本价、现价、盈亏%、盈亏额
- 资金曲线图
- 交易历史表

---

## 第7步：集成测试

### 端到端测试脚本 `test_integration.py`

```python
from core.data_manager import DataManager
from core.indicators import add_all_indicators
from core.backtest_engine import BacktestEngine
from core.portfolio import PortfolioManager
from strategies.trend_follow import TrendFollowStrategy
from strategies.mean_revert import MeanRevertStrategy
from strategies.momentum import MomentumStrategy

dm = DataManager()
df = dm.get_daily('000001', '20230101', '20241231')
df = add_all_indicators(df)

for Strat in [TrendFollowStrategy, MeanRevertStrategy, MomentumStrategy]:
    s = Strat()
    df_sig = s.generate_signals(df.copy())
    engine = BacktestEngine(100000)
    result = engine.run(df_sig, '000001')
    m = result['metrics']
    print(f"{s.__class__.__name__}: 总收益={m['total_return']:.2%} "
          f"夏普={m['sharpe_ratio']:.2f} 胜率={m['win_rate']:.2%} "
          f"最大回撤={m['max_drawdown']:.2%} 交易{m['total_trades']}次")
```

运行：`python test_integration.py`，输出三套策略的回测结果。

---

## 第8步：CI 定时信号系统（GitHub Actions）

### 8.1 新增文件清单

| 文件 | 用途 |
|------|------|
| `.github/workflows/intraday.yml` | 盘中信号（高频） |
| `.github/workflows/daily.yml` | 日终报告 |
| `ci/run_signals.py` | CI入口：拉数据→跑策略→输出JSON |
| `ci/generate_report.py` | JSON→HTML报告 |
| `config/monitor_stocks.csv` | 监控股票池 |
| `.gitignore` | 忽略 data/cache 等 |

### 8.2 `ci/run_signals.py` 实现要求

**输入**：`config/monitor_stocks.csv`（默认5只股票）

**流程**：
1. 读取监控股票池 CSV
2. 对每只股票调用 `DataManager.get_daily(code, start_date=一年前, end_date=今天)`（无缓存，CI环境）
3. 计算指标 `add_all_indicators(df)`
4. 用默认参数跑 `TrendFollowStrategy` 和 `MomentumStrategy`
5. 合并信号，对每只股票取最新交易日的信号
6. 额外拉取大盘指数（上证000001.SH、深证399001.SZ）作为 market_summary
7. 输出 `signals/latest.json` + `signals/{YYYYMMDD}.json`

**JSON结构**（严格按 CI_ARCHITECTURE.md 第4.1节格式）。

**注意**：
- 必须在CI和本地都能运行（不依赖 streamlit）
- 需要 `if __name__ == "__main__":` 入口
- 失败时输出错误JSON，退出码非0（让Actions发告警）

### 8.3 `ci/generate_report.py` 实现要求

**输入**：`signals/latest.json`

**流程**：
1. 读取JSON
2. 用Python字符串模板生成HTML（**不依赖前端框架**）
3. 卡片式布局：每只股票一张卡片，BUY绿色/SELL红色/HOLD灰色
4. 生成 `public/index.html`
5. 生成历史归档 `public/history/{YYYYMMDD}.html`

**HTML要求**：
- 纯静态，无外部CDN依赖（CI环境可能受限）
- 内联CSS，中文友好
- 手机端适配（响应式）

### 8.4 监控股票池 `config/monitor_stocks.csv`

```csv
code,name
600519,贵州茅台
000001,平安银行
300750,宁德时代
601318,中国平安
600036,招商银行
```

### 8.5 Workflow 文件

严格按 CI_ARCHITECTURE.md 第3.2/3.3节模板编写。关键点：
- cron 时间全部用 UTC（BJT-8）
- `workflow_dispatch` 必须加上（方便手动触发测试）
- `permissions` 三行必须写全（contents/pages/id-token）
- `concurrency` 防止并发覆盖
- 完成后在仓库 Settings→Pages 选择"GitHub Actions"作为发布源

### 8.6 验证方式

1. 本地运行：`python ci/run_signals.py` 生成 signals/latest.json
2. 本地运行：`python ci/generate_report.py` 打开 public/index.html 检查
3. 推送后到 Actions 页面手动触发 `workflow_dispatch` 验证
4. 首次部署后访问 `https://{用户名}.github.io/a-share-signals/` 检查

---

## 实现顺序总结

| 步骤 | 文件 | 预计代码行数 | 依赖 |
|------|------|-------------|------|
| 0 | requirements.txt, config/settings.py, 目录结构 | ~20 | 无 |
| 1 | core/data_manager.py | ~120 | akshare, pandas |
| 2 | core/indicators.py | ~80 | pandas, pandas-ta |
| 3 | core/strategy_base.py | ~25 | pandas |
| 3 | strategies/trend_follow.py | ~100 | strategy_base |
| 3 | strategies/mean_revert.py | ~100 | strategy_base |
| 3 | strategies/momentum.py | ~90 | strategy_base |
| 3 | strategies/multi_factor.py | ~150 | strategy_base |
| 4 | core/backtest_engine.py | ~180 | indicators |
| 5 | core/portfolio.py | ~150 | 无 |
| 6 | app.py | ~20 | streamlit, ui |
| 6 | ui/page_data.py | ~120 | data_manager, indicators, plotly |
| 6 | ui/page_backtest.py | ~200 | data_manager, backtest_engine, strategies, plotly |
| 6 | ui/page_paper_trading.py | ~200 | data_manager, portfolio, strategies, plotly |
| 7 | test_integration.py | ~30 | 全部 |
| 8 | .github/workflows/intraday.yml + daily.yml | ~80 (yaml) | CI脚本 |
| 8 | ci/run_signals.py | ~150 | data_manager, strategies |
| 8 | ci/generate_report.py | ~120 | 无 |
| 8 | config/monitor_stocks.csv | ~5 | 无 |
| **总计** | **约2000行Python + 80行YAML** | | |

---

## 实现约束（必须遵守）

1. **不要添加任何注释**（`#` 开头的行）。代码通过命名自解释。
2. **所有函数和类使用 type hints**（如 `def x(y: str) -> pd.DataFrame:`）。
3. **文件编码UTF-8**，首行不需要 `# -*- coding: utf-8 -*-`（Python 3默认）。
4. **不要使用 `print`**，使用 `logging` 或 Streamlit 的 `st.info/warning/error`。
5. **不要提前优化**。先实现功能，正确性优先于性能。
6. **每个文件独立可测**。不依赖其他未实现的文件。
7. **所有文件顶部导入**，不在函数内部导入。
8. **不要使用 `from x import *`**，显式导入所需符号。
