import os
import re
from datetime import datetime
from typing import Optional

import akshare as ak
import pandas as pd
import requests

from config.settings import CACHE_DIR


class DataFetchError(Exception):
    pass


class DataManager:
    _TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    _FALLBACK_NAMES = {
        "600519": "贵州茅台",
        "000001": "平安银行",
        "300750": "宁德时代",
        "601318": "中国平安",
        "600036": "招商银行",
        "600030": "中信证券",
        "000858": "五粮液",
        "601899": "紫金矿业",
        "600900": "长江电力",
        "601398": "工商银行",
        "601288": "农业银行",
        "600276": "恒瑞医药",
        "002594": "比亚迪",
        "601012": "隆基绿能",
        "002415": "海康威视",
        "000333": "美的集团",
        "600887": "伊利股份",
        "603288": "海天味业",
        "300059": "东方财富",
        "601888": "中国中免",
    }

    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        self.daily_dir = os.path.join(cache_dir, "daily")
        self.stock_list_path = os.path.join(cache_dir, "stock_list.csv")
        os.makedirs(self.daily_dir, exist_ok=True)

    def standardize_code(self, code: str) -> str:
        digits = re.sub(r"\D", "", str(code))
        if not digits:
            raise DataFetchError(f"股票代码 {code} 无效")
        return digits.zfill(6)

    def get_daily(
        self,
        stock_code: str,
        start_date: str = "20150101",
        end_date: Optional[str] = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        code = self.standardize_code(stock_code)
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        cache_path = os.path.join(self.daily_dir, f"{code}.csv")

        cached_df = None
        if use_cache and os.path.exists(cache_path):
            try:
                cached_df = self._read_csv(cache_path)
            except Exception:
                os.remove(cache_path)
                cached_df = None

        if cached_df is not None and not cached_df.empty:
            latest = cached_df["date"].max().strftime("%Y%m%d")
            earliest = cached_df["date"].min().strftime("%Y%m%d")
            if earliest <= start_date and latest >= end_date:
                return self._slice(cached_df, start_date, end_date)
            if latest >= end_date:
                return self._slice(cached_df, start_date, end_date)
            fetch_start = latest
            df_new = self._fetch(code, fetch_start, end_date)
            if df_new is not None and not df_new.empty:
                merged = self._merge_cache(cached_df, df_new)
                self._write_csv(merged, cache_path)
                return self._slice(merged, start_date, end_date)
            if not cached_df.empty:
                return self._slice(cached_df, start_date, end_date)
            raise DataFetchError(f"股票代码 {code} 无数据")

        df = self._fetch(code, start_date, end_date)
        if df is None or df.empty:
            raise DataFetchError(f"股票代码 {code} 无数据")
        if use_cache:
            self._write_csv(df, cache_path)
        return df

    def _fetch(self, code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        last_error = None
        for attempt in range(3):
            try:
                df = self._fetch_tencent(code, start_date, end_date)
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                last_error = e
            try:
                raw = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq",
                )
                df = self._standardize(raw)
                if not df.empty:
                    return df
            except Exception as e:
                last_error = e
        if last_error is not None:
            raise DataFetchError(f"股票代码 {code} 数据获取失败: {last_error}")
        raise DataFetchError(f"股票代码 {code} 数据获取失败")

    def _fetch_tencent(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        market = "sh" if code.startswith("6") else "sz"
        symbol = f"{market}{code}"
        params = {"param": f"{symbol},day,{self._fmt(start_date)},{self._fmt(end_date)},640,qfq"}
        last_error = None
        for attempt in range(3):
            try:
                r = requests.get(
                    self._TENCENT_KLINE_URL,
                    params=params,
                    timeout=15,
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"},
                )
                r.raise_for_status()
                data = r.json()
                stock = data.get("data", {}).get(symbol, {})
                klines = stock.get("qfqday") or stock.get("day") or []
                if not klines:
                    return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
                rows = []
                for k in klines:
                    amount = 0.0
                    if len(k) > 6 and isinstance(k[6], (int, float, str)):
                        try:
                            amount = float(k[6])
                        except (TypeError, ValueError):
                            amount = 0.0
                    rows.append(
                        {
                            "date": pd.to_datetime(k[0]),
                            "open": float(k[1]),
                            "high": float(k[3]),
                            "low": float(k[4]),
                            "close": float(k[2]),
                            "volume": float(k[5]),
                            "amount": amount,
                        }
                    )
                df = pd.DataFrame(rows)
                return df.sort_values("date").reset_index(drop=True)
            except Exception as e:
                last_error = e
        raise DataFetchError(f"腾讯K线获取失败: {last_error}")

    @staticmethod
    def _fmt(date_str: str) -> str:
        d = pd.to_datetime(date_str)
        return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"

    def _standardize(self, raw: pd.DataFrame) -> pd.DataFrame:
        if raw is None or raw.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
        column_map = {
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "成交额": "amount",
        }
        df = raw.rename(columns=column_map)
        keep = ["date", "open", "high", "low", "close", "volume", "amount"]
        df = df[[c for c in keep if c in df.columns]]
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        return df

    def _read_csv(self, path: str) -> pd.DataFrame:
        df = pd.read_csv(path, parse_dates=["date"])
        return df.sort_values("date").reset_index(drop=True)

    def _write_csv(self, df: pd.DataFrame, path: str) -> None:
        df.to_csv(path, index=False, encoding="utf-8")

    def _merge_cache(self, old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
        merged = pd.concat([old, new], ignore_index=True)
        merged = merged.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
        return merged

    def _slice(self, df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)

    def get_stock_list(self) -> pd.DataFrame:
        if os.path.exists(self.stock_list_path):
            mtime = os.path.getmtime(self.stock_list_path)
            if datetime.now().timestamp() - mtime < 86400:
                df = pd.read_csv(self.stock_list_path, dtype={"code": str})
                df["code"] = df["code"].str.zfill(6)
                return df
        try:
            raw = ak.stock_zh_a_spot_em()
            if raw is not None and not raw.empty:
                df = raw.rename(
                    columns={
                        "代码": "code",
                        "名称": "name",
                        "最新价": "price",
                        "涨跌幅": "pct_change",
                        "成交量": "volume",
                        "成交额": "amount",
                        "市盈率-动态": "pe",
                    }
                )
                keep = ["code", "name", "price", "pct_change", "volume", "amount", "pe"]
                df = df[[c for c in keep if c in df.columns]]
                df["code"] = df["code"].astype(str).str.zfill(6)
                df.to_csv(self.stock_list_path, index=False, encoding="utf-8")
                return df
        except Exception:
            pass
        if os.path.exists(self.stock_list_path):
            return pd.read_csv(self.stock_list_path, dtype={"code": str})
        return pd.DataFrame(columns=["code", "name"])

    def get_stock_name(self, stock_code: str) -> str:
        code = self.standardize_code(stock_code)
        df = self.get_stock_list()
        if df is not None and not df.empty:
            match = df[df["code"] == code]
            if not match.empty:
                return str(match.iloc[0]["name"])
        return self._FALLBACK_NAMES.get(code, code)

    def get_realtime_price(self, stock_code: str) -> dict:
        code = self.standardize_code(stock_code)
        market = "sh" if code.startswith("6") else "sz"
        symbol = f"{market}{code}"
        try:
            r = requests.get(
                f"https://qt.gtimg.cn/q={symbol}",
                timeout=10,
                headers={"Referer": "https://gu.qq.com/"},
            )
            r.raise_for_status()
            text = r.text
            quote = text.split('"')[1] if '"' in text else ""
            fields = quote.split("~")
            if len(fields) > 3:
                return {"code": code, "price": float(fields[3])}
            raise DataFetchError(f"股票代码 {code} 实时行情解析失败")
        except DataFetchError:
            raise
        except Exception:
            raise DataFetchError(f"股票代码 {code} 实时行情获取失败")

    def get_index_daily(self, symbol: str, start_date: str = "20240101") -> pd.DataFrame:
        params = {"param": f"{symbol},day,{self._fmt(start_date)},{datetime.now().strftime('%Y-%m-%d')},640,"}
        last_error = None
        for attempt in range(3):
            try:
                r = requests.get(
                    self._TENCENT_KLINE_URL,
                    params=params,
                    timeout=15,
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"},
                )
                r.raise_for_status()
                data = r.json()
                klines = data.get("data", {}).get(symbol, {}).get("day") or []
                if not klines:
                    raise DataFetchError(f"指数 {symbol} 数据获取失败")
                rows = []
                for k in klines:
                    rows.append(
                        {
                            "date": pd.to_datetime(k[0]),
                            "open": float(k[1]),
                            "high": float(k[3]),
                            "low": float(k[4]),
                            "close": float(k[2]),
                            "volume": float(k[5]),
                        }
                    )
                df = pd.DataFrame(rows)
                return df.sort_values("date").reset_index(drop=True)
            except Exception as e:
                last_error = e
        raise DataFetchError(f"指数 {symbol} 数据获取失败: {last_error}")

    def clear_cache(self, stock_code: Optional[str] = None) -> None:
        if stock_code is None:
            for f in os.listdir(self.daily_dir):
                os.remove(os.path.join(self.daily_dir, f))
            if os.path.exists(self.stock_list_path):
                os.remove(self.stock_list_path)
        else:
            path = os.path.join(self.daily_dir, f"{self.standardize_code(stock_code)}.csv")
            if os.path.exists(path):
                os.remove(path)
