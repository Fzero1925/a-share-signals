import datetime
from typing import Optional

import pandas as pd

# A股 2026 年法定休市日（周末 + 节假日）
# 来源：上交所/深交所 2026 年休市安排
HOLIDAYS_2026 = {
    "2026-01-01",  # 元旦
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-23",  # 春节
    "2026-04-06",  # 清明
    "2026-05-01",  # 劳动节
    "2026-05-04", "2026-05-05",  # 劳动节
    "2026-06-19",  # 端午
    "2026-09-25",  # 中秋
    "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08",  # 国庆
}

HOLIDAYS_2027 = {
    "2027-01-01",
    "2027-02-15", "2027-02-16", "2027-02-17", "2027-02-18", "2027-02-19", "2027-02-22",
    "2027-04-05",
    "2027-05-03", "2027-05-04", "2027-05-05",
    "2027-06-14",
    "2027-09-17",
    "2027-10-01", "2027-10-04", "2027-10-05", "2027-10-06", "2027-10-07", "2027-10-08",
}

HOLIDAYS = HOLIDAYS_2026 | HOLIDAYS_2027


def is_trading_day(date: Optional[datetime.date] = None) -> bool:
    if date is None:
        date = datetime.date.today()
    if date.weekday() >= 5:
        return False
    return date.isoformat() not in HOLIDAYS


def next_trading_day(date: Optional[datetime.date] = None) -> datetime.date:
    if date is None:
        date = datetime.date.today()
    d = date
    while not is_trading_day(d):
        d += datetime.timedelta(days=1)
    return d
