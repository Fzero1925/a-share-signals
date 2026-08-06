# 回测引擎规范

## 1. 回测原理

**事件驱动回测**：按交易日逐日遍历历史数据，每日检查策略信号，模拟执行交易。

## 2. A股交易规则模拟

### 2.1 T+1 制度
- 当日买入的股票，最早次日才能卖出
- 实现方式：买入当日 `position` 标记为1，卖出检查时用 `entry_date < current_date`

### 2.2 涨跌停处理
```python
def can_buy(close, pre_close, stock_code):
    """检查能否买入（是否涨停）"""
    limit_pct = 0.20 if stock_code.startswith(('300','688')) else 0.10
    limit_up = pre_close * (1 + limit_pct)
    return close < limit_up  # 涨停价无法买入（买不到）

def can_sell(close, pre_close, stock_code):
    """检查能否卖出（是否跌停）"""
    limit_pct = 0.20 if stock_code.startswith(('300','688')) else 0.10
    limit_down = pre_close * (1 - limit_pct)
    return close > limit_down  # 跌停价无法卖出（卖不出）
```

### 2.3 交易费用
```python
STAMP_TAX = 0.001       # 印花税 0.1%（仅卖出）
COMMISSION = 0.0003     # 佣金 0.03%（买卖双向，最低5元）
TRANSFER_FEE = 0.00002  # 过户费 0.002%（买卖双向）
MIN_COMMISSION = 5.0    # 最低佣金5元

def calc_cost(price, shares, action):
    """action: 'buy' 或 'sell'"""
    amount = price * shares
    commission = max(amount * COMMISSION, MIN_COMMISSION)
    transfer = amount * TRANSFER_FEE
    stamp = amount * STAMP_TAX if action == 'sell' else 0
    return commission + transfer + stamp
```

### 2.4 成交价格假设
- 回测中使用当日**收盘价**作为成交价（保守假设）
- 非涨停卖出/跌停买入用当日收盘价

## 3. BacktestEngine 接口

```python
class BacktestEngine:
    def __init__(self, initial_capital: float = 100000.0):
        """
        initial_capital: 初始资金(元)
        """

    def run(
        self,
        df: pd.DataFrame,          # 含OHLCV + signal列的DataFrame
        stock_code: str = "000001",
        position_pct: float = 0.3,  # 单次买入仓位比例
    ) -> dict:
        """
        执行回测
        返回: {
            'trades': pd.DataFrame,       # 交易明细
            'equity_curve': pd.DataFrame, # 每日权益
            'metrics': dict,              # 绩效指标
            'df': pd.DataFrame,           # 含position列的原始数据
        }
        """

    def calc_metrics(self, equity_curve: pd.DataFrame, trades: pd.DataFrame) -> dict:
        """
        计算绩效指标
        见下方"绩效指标公式"
        """
```

## 4. 回测执行流程（伪代码）

```python
def run(df, stock_code, position_pct):
    cash = initial_capital           # 可用现金
    holding_shares = 0               # 持仓股数
    entry_price = 0                  # 买入价
    entry_date = None                # 买入日期
    highest_since_entry = 0          # 持仓期间最高价
    trades = []                      # 交易记录
    equity = []                      # 每日权益
    
    for i, (idx, row) in enumerate(df.iterrows()):
        date = row['date']
        close = row['close']
        pre_close = df.iloc[i-1]['close'] if i > 0 else close
        signal = row['signal']
        
        # 计算当日权益
        market_value = holding_shares * close
        total_equity = cash + market_value
        
        if signal == 1 and holding_shares == 0:   # 买入信号 + 空仓
            if can_buy(close, pre_close, stock_code):
                buy_amount = total_equity * position_pct
                shares = int(buy_amount / close / 100) * 100
                if shares >= 100:
                    cost = calc_cost(close, shares, 'buy')
                    cash = cash - close * shares - cost
                    holding_shares = shares
                    entry_price = close
                    entry_date = date
                    highest_since_entry = close
                    trades.append({'date': date, 'action': 'BUY', ...})
        
        elif signal == -1 and holding_shares > 0:  # 卖出信号 + 持仓
            if can_sell(close, pre_close, stock_code):
                sell_amount = close * holding_shares
                cost = calc_cost(close, holding_shares, 'sell')
                cash = cash + sell_amount - cost
                trades.append({'date': date, 'action': 'SELL', ...})
                holding_shares = 0
                entry_price = 0
        
        # 更新持仓期间最高价
        if holding_shares > 0 and close > highest_since_entry:
            highest_since_entry = close
        
        equity.append({'date': date, 'equity': total_equity, 'position': holding_shares > 0})
    
    return {'trades': trades, 'equity_curve': equity, 'metrics': metrics}
```

## 5. 绩效指标公式

```python
def calc_metrics(equity_curve, trades, initial_capital):
    returns = equity_curve['equity'].pct_change().dropna()
    
    total_return = (equity_curve['equity'].iloc[-1] / initial_capital) - 1
    
    # 年化收益率: 按实际交易日折算
    trading_days = len(equity_curve)
    years = trading_days / 252
    annual_return = (1 + total_return) ** (1 / years) - 1
    
    # 最大回撤
    cummax = equity_curve['equity'].cummax()
    drawdown = (equity_curve['equity'] - cummax) / cummax
    max_drawdown = drawdown.min()
    
    # 夏普比率 (无风险利率 2%)
    rf_daily = 0.02 / 252
    excess = returns - rf_daily
    sharpe = np.sqrt(252) * excess.mean() / excess.std() if excess.std() > 0 else 0
    
    # 胜率
    buy_trades = [t for t in trades if t['action'] == 'BUY']
    sell_trades = [t for t in trades if t['action'] == 'SELL']
    wins = sum(1 for s in sell_trades if s['price'] > buy_trades[对应].price)
    win_rate = wins / len(sell_trades) if sell_trades else 0
    
    # 盈亏比
    avg_win = mean of profitable trades' return
    avg_loss = abs(mean of losing trades' return)
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
    
    # 总交易次数
    total_trades = len(buy_trades)
    
    return {
        'total_return': total_return,
        'annual_return': annual_return,
        'max_drawdown': max_drawdown,
        'sharpe_ratio': sharpe,
        'win_rate': win_rate,
        'profit_loss_ratio': profit_loss_ratio,
        'total_trades': total_trades,
    }
```

## 6. 回测结果输出

### 交易明细DataFrame列
```
date        action  price   shares  cost    pnl     pnl_pct
2024-01-15  BUY     10.50   1000    31.50   0       0
2024-01-28  SELL    11.20   1000    35.60   633.90  0.0604
```

### 权益曲线DataFrame列
```
date        equity    cash      position_value  drawdown
2024-01-01  100000.0  100000.0  0               0
2024-01-15  100000.0  89468.5   10500.0         0
2024-01-28  100633.9  100633.9  0               0
```
