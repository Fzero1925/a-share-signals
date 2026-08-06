# 交易策略规范 — 精确公式与参数

## 策略设计原则

1. **可解释**：每个信号有明确的触发条件
2. **可复现**：给定相同数据，信号永远一致
3. **防过拟合**：参数有合理区间，不做过度优化
4. **A股适配**：考虑T+1、涨跌停、散户跟随特点

---

## 策略1：趋势跟踪 — Dual EMA + ADX 过滤

**适用场景**：单边上涨/下跌行情，日线级别
**持仓周期**：3-20个交易日
**风格**：中线趋势

### 指标参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| fast_ema | 5 | 快线周期 |
| slow_ema | 20 | 慢线周期 |
| adx_period | 14 | ADX计算周期 |
| adx_threshold | 25 | ADX阈值，低于此值不做交易(震荡市过滤) |
| stop_loss_pct | 0.05 | 固定止损比例 |
| trailing_stop_pct | 0.03 | 移动止损：从最高点回落3% |
| take_profit_pct | 0.15 | 止盈比例 |

### 信号公式

```
EMA_fast = EMA(close, fast_ema)
EMA_slow = EMA(close, slow_ema)
ADX = ADX(high, low, close, adx_period)

### 买入信号 (BUY)
条件:
  1. EMA_fast[t] > EMA_slow[t]           # 快线上穿慢线(金叉当日)
  2. EMA_fast[t-1] <= EMA_slow[t-1]      # 确保是交叉日
  3. ADX[t] >= adx_threshold             # 趋势强度足够
  4. close[t] > EMA_slow[t]              # 价格在慢线上方

### 卖出信号 (SELL)
条件（满足任一）:
  1. EMA_fast[t] < EMA_slow[t]           # 死叉
  2. close[t] <= entry_price * (1 - stop_loss_pct)     # 固定止损
  3. close[t] <= highest_since_entry * (1 - trailing_stop_pct)  # 移动止损
  4. close[t] >= entry_price * (1 + take_profit_pct)   # 止盈
```

### 仓位计算
```
买入金额 = 总资金 * 0.3          # 单票仓位上限30%
买入股数 = floor(买入金额 / (close * 100)) * 100   # 取整手
```

---

## 策略2：均值回归 — Bollinger Bands + RSI

**适用场景**：震荡市，日线级别
**持仓周期**：1-7个交易日
**风格**：短线反弹

### 指标参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| bb_period | 20 | 布林带周期 |
| bb_std | 2.0 | 标准差倍数 |
| rsi_period | 14 | RSI周期 |
| rsi_oversold | 35 | 超卖阈值 |
| rsi_overbought | 65 | 超买阈值 |
| stop_loss_pct | 0.03 | 止损 |
| take_profit_pct | 0.05 | 止盈 |

### 信号公式

```
BB_mid = MA(close, bb_period)
BB_upper = BB_mid + bb_std * STD(close, bb_period)
BB_lower = BB_mid - bb_std * STD(close, bb_period)
RSI = RSI(close, rsi_period)
BB_width = (BB_upper - BB_lower) / BB_mid   # 带宽，衡量波动

### 买入信号 (BUY)
条件:
  1. close[t] <= BB_lower[t] * 1.01       # 价格触及或轻微跌破下轨
  2. RSI[t] < rsi_oversold                # RSI超卖
  3. BB_width[t] > 0.05                   # 带宽足够(有波动才有回归空间)
  4. close[t] > close[t-1]               # 当日收阳（确认反弹）

### 卖出信号 (SELL)
条件（满足任一）:
  1. close[t] >= BB_mid[t]                # 回归中轨即卖
  2. RSI[t] > rsi_overbought              # RSI超买
  3. close[t] <= entry_price * (1 - stop_loss_pct)  # 止损
  4. 持仓超过7天强制平仓                    # 时间止损
```

### 仓位计算
```
买入金额 = min(总资金 * 0.2, 总资金 * BB_width * 5)  # 波动越大仓位越大
买入股数 = floor(买入金额 / close) 向下取整到100的倍数
```

---

## 策略3：动量突破 — 阶段新高 + 放量确认

**适用场景**：强势突破行情，日线级别
**持仓周期**：3-15个交易日
**风格**：短线追涨

### 指标参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| lookback_high | 20 | 新高回溯周期 |
| lookback_low | 10 | 新低回溯周期 |
| volume_ma | 20 | 成交量均线周期 |
| volume_ratio | 1.5 | 放量倍数阈值 |
| stop_loss_pct | 0.05 | 止损 |
| trailing_stop_pct | 0.04 | 移动止损 |

### 信号公式

```
high_N = MAX(close, lookback_high)          # N日最高收盘价
low_M = MIN(close, lookback_low)            # M日最低收盘价
vol_ma = MA(volume, volume_ma)
vol_ratio = volume / vol_ma

### 买入信号 (BUY)
条件:
  1. close[t] > high_N[t-1]                  # 突破前N日最高价
  2. vol_ratio[t] >= volume_ratio             # 成交量放大确认
  3. close[t] > MA(close, 60)                 # 中长期趋势向上（60日均线之上）

### 卖出信号 (SELL)
条件（满足任一）:
  1. close[t] < MA(close, 10)                 # 跌破10日线
  2. close[t] <= low_M[t-1]                   # 跌破M日最低价
  3. close[t] <= entry_price * (1 - stop_loss_pct)
  4. close[t] <= highest_since_entry * (1 - trailing_stop_pct)
```

### 仓位计算
```
买入金额 = 总资金 * 0.25
买入股数 = floor(买入金额 / close) 向下取整到100的倍数
```

---

## 策略4：多因子打分轮动

**适用场景**：股票池选股，周频调仓
**持仓周期**：1-4周
**风格**：中线轮动

### 因子定义

| 因子名称 | 权重 | 计算方法 | 方向 |
|----------|------|----------|------|
| momentum_20d | 0.25 | (close[t] / close[t-20] - 1) | 正向 |
| volatility_20d | 0.15 | -1 * STD(return, 20) | 反向(低波动加分) |
| volume_ratio_5d | 0.20 | volume[t] / MA(volume, 20) | 正向 |
| trend_strength | 0.25 | (close - MA_60) / MA_60 | 正向 |
| rsi_score | 0.15 | (RSI_14 - 50) / 50 | 正向(50以上加分) |

### 打分流程

```
对股票池中每只股票:
  1. 计算5个因子的原始值
  2. 每个因子对全市场做 百分位排名(percentile rank, 0到1)
  3. 加权求和: score = Σ(weight_i * rank_i)
  4. 按score降序排列
  5. 买入score最高的前N只股票（N=5）
  
每周最后一个交易日收盘前调仓:
  1. 卖出不在新top N中的持仓
  2. 买入新进入top N的股票
  3. 等权重分配资金
```

### 过滤条件
- 剔除ST、*ST股票（代码含ST）
- 剔除上市不满60个交易日的次新股
- 剔除当日停牌股（volume=0或close无变化）
- 剔除涨跌停无法交易的股票

---

## 策略公共接口规范

每个策略文件必须实现以下接口：

```python
class BaseStrategy:
    def __init__(self, params: dict):
        """params为参数字典，键值见各策略参数表"""
        self.params = params
        self.name = "策略名称"  # 子类必须设置

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        输入: 包含OHLCV的DataFrame
        输出: 原DataFrame增加两列:
          - signal: int, 1=买入, -1=卖出, 0=无操作
          - position: int, 1=持仓, 0=空仓
        注意: 此函数只生成信号，不处理仓位管理
        """
        pass

    def get_default_params() -> dict:
        """返回默认参数字典"""
        pass
```
