# 模拟盘（虚拟账户）管理规范

## 1. 职责

PortfolioManager 管理一个虚拟交易账户：
- 追踪现金余额和持仓
- 记录每笔交易
- 计算实时浮动盈亏
- 输出账户快照

## 2. 接口规范

```python
class PortfolioManager:
    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}        # {stock_code: {'shares': int, 'entry_price': float, 'entry_date': str}}
        self.trade_history = []    # 交易记录列表
        self.equity_history = []   # 每日权益快照

    def buy(
        self,
        stock_code: str,
        price: float,
        shares: int,
        date: str,
        reason: str = ""
    ) -> bool:
        """
        买入股票
        shares: 必须是100的整数倍
        price: 成交价
        返回: True=成功, False=失败(资金不足/持仓已存在)
        自动扣除手续费
        """

    def sell(
        self,
        stock_code: str,
        price: float,
        date: str,
        reason: str = ""
    ) -> bool:
        """
        卖出全部持仓
        返回: True=成功, False=失败(无持仓)
        自动扣除手续费，计算已实现盈亏
        """

    def get_position(self, stock_code: str) -> dict:
        """获取单只股票持仓信息"""

    def get_all_positions(self) -> dict:
        """获取全部持仓"""

    def get_total_equity(self, current_prices: dict) -> float:
        """
        计算总权益
        current_prices: {stock_code: latest_price}
        总权益 = 现金 + sum(持仓股数 * 最新价)
        """

    def get_equity_history(self) -> pd.DataFrame:
        """获取每日权益历史"""

    def get_trade_history(self) -> pd.DataFrame:
        """获取交易历史"""

    def get_performance(self, current_prices: dict) -> dict:
        """
        获取当前账户绩效
        返回: {
            'total_return': float,
            'total_profit': float,
            'win_trades': int,
            'loss_trades': int,
            'current_positions': int,
        }
        """

    def save_state(self, filepath: str):
        """保存账户状态到JSON文件"""

    def load_state(self, filepath: str):
        """从JSON文件恢复账户状态"""
```

## 3. 数据持久化

### 账户状态JSON格式
```json
{
    "initial_capital": 100000.0,
    "cash": 85234.50,
    "created_at": "2024-01-01 09:30:00",
    "updated_at": "2024-12-31 15:00:00",
    "positions": {
        "000001": {
            "shares": 1000,
            "entry_price": 10.50,
            "entry_date": "2024-12-15",
            "reason": "EMA金叉"
        }
    },
    "trade_history": [
        {
            "date": "2024-01-15",
            "code": "000001",
            "action": "BUY",
            "price": 10.50,
            "shares": 1000,
            "cost": 31.50,
            "reason": "EMA金叉"
        }
    ]
}
```

### 文件位置
```
data/
  portfolio/
    paper_account.json    # 模拟盘账户状态
    backtest_results/     # 回测结果存档
```

## 4. 模拟盘操作流程

```
1. 用户选择策略 + 股票池
2. 系统拉取最新K线数据
3. 策略生成最新信号
4. 用户确认要执行的交易（系统推荐，用户可覆盖）
5. 以当日收盘价或用户指定价成交
6. 记录交易，更新持仓
7. 次日/后续打开时，根据最新行情更新浮动盈亏
```

## 5. 模拟盘页面展示

- 当前持仓列表（代码、名称、股数、成本价、现价、盈亏%、盈亏额）
- 账户总览（总资产、现金、持仓市值、总收益率）
- 最近交易记录表
- 资金曲线图（权益 vs 基准沪深300）
