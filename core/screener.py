import re
import time
from typing import Optional

import pandas as pd
import requests

MIN_AMOUNT = 3e8
MAX_PAGES = 5
PAGE_SIZE = 100

_EM_CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
_EM_FIELDS = "f2,f3,f5,f6,f8,f12,f14,f15,f16,f17"
_SINA_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"


def _get_with_retry(url: str, params: dict, tries: int = 4, delay: float = 3.0) -> Optional[requests.Response]:
    for attempt in range(tries):
        try:
            r = requests.get(
                url,
                params=params,
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
            )
            r.raise_for_status()
            return r
        except Exception:
            if attempt == tries - 1:
                return None
            time.sleep(delay * (attempt + 1))
    return None


def _fetch_em_page(page: int) -> tuple[list, int]:
    r = _get_with_retry(
        _EM_CLIST_URL,
        {
            "pn": page,
            "pz": PAGE_SIZE,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f6",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": _EM_FIELDS,
        },
    )
    if r is None:
        return [], 0
    try:
        data = r.json().get("data", {})
        return data.get("diff", []), data.get("total", 0)
    except Exception:
        return [], 0


def _fetch_sina_page(page: int) -> list:
    r = _get_with_retry(
        _SINA_URL,
        {"page": page, "num": PAGE_SIZE, "sort": "amount", "asc": 0, "node": "hs_a", "_s_r_a": "init"},
    )
    if r is None:
        return []
    try:
        return r.json()
    except Exception:
        return []


def _sina_rows_to_df(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(
            columns=["code", "name", "price", "pct_change", "volume", "amount", "turnover", "high", "low", "open"]
        )
    df = pd.DataFrame(rows)
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["name"] = df["name"].astype(str)
    df["price"] = df["trade"].apply(_parse_value)
    df["pct_change"] = df["changepercent"].apply(_parse_value)
    df["amount"] = df["amount"].apply(_parse_value)
    df["volume"] = df["volume"].apply(_parse_value)
    df["turnover"] = df.get("turnoverratio")
    df["high"] = df["high"].apply(_parse_value)
    df["low"] = df["low"].apply(_parse_value)
    df["open"] = df["open"].apply(_parse_value)
    keep = ["code", "name", "price", "pct_change", "volume", "amount", "turnover", "high", "low", "open"]
    return df[keep].dropna(subset=["code", "price"]).reset_index(drop=True)


def _parse_value(v) -> Optional[float]:
    if v is None or v == "-":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _is_st(name: str) -> bool:
    return "ST" in name.upper() or "*ST" in name.upper()


def _is_new_stock(code: str, trade: Optional[float]) -> bool:
    if code.startswith("300") and trade is None:
        return False
    return False


def fetch_market_snapshot(max_pages: int = MAX_PAGES) -> pd.DataFrame:
    rows = []
    total = 0
    for page in range(1, max_pages + 1):
        diff, total = _fetch_em_page(page)
        if not diff:
            break
        rows.extend(diff)
        if len(rows) >= total:
            break
        if len(diff) < PAGE_SIZE:
            break
        time.sleep(1)

    if not rows:
        for page in range(1, max_pages + 1):
            sina_rows = _fetch_sina_page(page)
            if not sina_rows:
                break
            rows.extend(sina_rows)
            if len(sina_rows) < PAGE_SIZE:
                break
            time.sleep(1)
        if rows:
            return _sina_rows_to_df(rows)

    if not rows:
        return pd.DataFrame(
            columns=["code", "name", "price", "pct_change", "volume", "amount", "turnover", "high", "low", "open"]
        )
    df = pd.DataFrame(rows)
    df["code"] = df["f12"].astype(str).str.zfill(6)
    df["name"] = df["f14"].astype(str)
    df["price"] = df["f2"].apply(_parse_value)
    df["pct_change"] = df["f3"].apply(_parse_value)
    df["volume"] = df["f5"].apply(_parse_value)
    df["amount"] = df["f6"].apply(_parse_value)
    df["turnover"] = df["f8"].apply(_parse_value)
    df["high"] = df["f15"].apply(_parse_value)
    df["low"] = df["f16"].apply(_parse_value)
    df["open"] = df["f17"].apply(_parse_value)
    keep = ["code", "name", "price", "pct_change", "volume", "amount", "turnover", "high", "low", "open"]
    return df[keep].dropna(subset=["code", "price"]).reset_index(drop=True)


def build_candidate_pool(
    min_amount: float = MIN_AMOUNT,
    max_pages: int = MAX_PAGES,
    exclude_st: bool = True,
    exclude_limit_up: bool = True,
    exclude_limit_down: bool = True,
    max_candidates: int = 300,
) -> pd.DataFrame:
    df = fetch_market_snapshot(max_pages=max_pages)
    if df.empty:
        return df

    if exclude_st:
        df = df[~df["name"].apply(_is_st)]

    df = df[df["amount"].notna()]

    df = df[df["amount"] >= min_amount]

    df = df.sort_values("amount", ascending=False)

    if exclude_limit_up:
        df = df[df["pct_change"] < 9.5]
    if exclude_limit_down:
        df = df[df["pct_change"] > -9.5]

    df = df.head(max_candidates).reset_index(drop=True)
    return df


def build_candidate_pool_from_list(
    codes: list[str],
    min_amount: float = MIN_AMOUNT,
    exclude_st: bool = True,
) -> pd.DataFrame:
    df = fetch_market_snapshot(max_pages=MAX_PAGES)
    if df.empty:
        return df
    df = df[df["code"].isin(codes)]
    if exclude_st:
        df = df[~df["name"].apply(_is_st)]
    return df.reset_index(drop=True)
