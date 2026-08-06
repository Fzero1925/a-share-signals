# 数据层规范

## 1. 数据源：AKShare

AKShare 是一个免费开源的Python金融数据接口库。
- 文档：https://akshare.akfamily.xyz
- 安装：`pip install akshare`
- 无需API Key，直接调用

### 1.1 日线数据获取

```python
import akshare as ak

# 获取A股日线数据
df = ak.stock_zh_a_hist(
    symbol="000001",       # 股票代码（不带后缀）
    period="daily",        # 日线
    start_date="20200101", # 起始日期 YYYYMMDD
    end_date="20241231",   # 结束日期 YYYYMMDD
    adjust="qfq"           # 前复权
)
```

### 1.2 AKShare返回的DataFrame列映射

| AKShare原始列名 | 标准列名 | 类型 |
|----------------|----------|------|
| 日期 | date | datetime64 |
| 开盘 | open | float64 |
| 最高 | high | float64 |
| 最低 | low | float64 |
| 收盘 | close | float64 |
| 成交量 | volume | float64 (单位：手) |
| 成交额 | amount | float64 (单位：元) |
| 振幅 | amplitude | float64 |
| 涨跌幅 | pct_change | float64 |
| 涨跌额 | change | float64 |
| 换手率 | turnover | float64 |

### 1.3 股票列表获取

```python
# 获取A股实时行情(含所有股票)
df = ak.stock_zh_a_spot_em()   # 东方财富实时行情
# 列：代码, 名称, 最新价, 涨跌幅, 成交量, 成交额, 换手率, 市盈率等
```

### 1.4 备用数据源

当AKShare不可用时，自动尝试：
1. **Tushare** (需token，免费注册获取)：`ts.pro_bar()`
2. 从本地缓存读取前两天数据（陈旧数据提示）

## 2. 本地缓存策略

### 2.1 缓存位置
```
data/cache/
  ├── daily/              # 日线数据
  │   ├── 000001.csv
  │   ├── 600000.csv
  │   └── ...
  └── stock_list.csv      # 股票列表缓存
```

### 2.2 缓存逻辑

```
DataManager.get_daily(stock_code, start_date, end_date):
  1. 检查本地缓存文件 data/cache/daily/{stock_code}.csv
  2. 如果缓存存在:
     a. 读取CSV
     b. 检查缓存最新日期 >= end_date
     c. 如果缓存数据覆盖请求范围，直接返回
     d. 如果缓存数据不够新，只拉取缺失日期段，合并
  3. 如果缓存不存在:
     a. 调用AKShare获取全量
     b. 保存到缓存
  4. 返回标准化的DataFrame
  5. 如果AKShare失败，返回缓存中的陈旧数据 + 警告
```

### 2.3 缓存CSV格式

```csv
date,open,high,low,close,volume,amount
2024-01-02,10.50,10.80,10.30,10.65,500000,530000000
2024-01-03,10.65,10.90,10.50,10.75,450000,480000000
```

- 编码: UTF-8
- 分隔符: 逗号
- 日期格式: YYYY-MM-DD
- 按日期升序排列

## 3. DataManager 接口规范

```python
class DataManager:
    def __init__(self, cache_dir: str = "data/cache"):
        """初始化，设置缓存目录"""

    def get_daily(
        self,
        stock_code: str,
        start_date: str = "20150101",
        end_date: str = None,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        获取日线数据
        stock_code: 6位数字字符串，如 '000001'
        start_date: YYYYMMDD
        end_date: YYYYMMDD，None表示到最新交易日
        use_cache: 是否使用缓存
        返回: 标准化DataFrame，按date升序
        异常: 股票代码无效或数据源全部不可用时 raise DataFetchError
        """

    def get_stock_list(self) -> pd.DataFrame:
        """
        获取A股股票列表
        返回: DataFrame with columns ['code', 'name', 'price', 'pct_change', 'pe']
        缓存: 股票列表缓存24小时
        """

    def get_realtime_price(self, stock_code: str) -> dict:
        """
        获取单只股票实时行情（用于模拟盘最新价格）
        返回: {'code': '000001', 'name': '平安银行', 'price': 10.50, ...}
        """

    def standardize_code(self, code: str) -> str:
        """
        标准化股票代码为6位字符串
        输入: '1', '000001', 'sh000001', 'SZ000001'
        输出: '000001'
        """

    def clear_cache(self, stock_code: str = None):
        """清除缓存，stock_code为None则清除全部"""
```

## 4. 错误处理

| 错误场景 | 处理方式 |
|----------|----------|
| 股票代码不存在 | raise DataFetchError(f"股票代码 {code} 无效") |
| AKShare网络超时(10s) | 尝试备用数据源，都失败则raise |
| 缓存文件损坏 | 删除缓存文件，重新拉取 |
| 日期范围无数据 | 返回空DataFrame + Streamlit warning |
| 停牌期间数据 | AKShare返回的数据中，停牌日无记录，正常处理 |
