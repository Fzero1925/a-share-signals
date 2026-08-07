from typing import Type

from core.strategy_base import BaseStrategy
from strategies.daily_momentum import DailyMomentumStrategy
from strategies.mean_revert import MeanRevertStrategy
from strategies.momentum import MomentumStrategy
from strategies.multi_factor import MultiFactorStrategy
from strategies.trend_follow import TrendFollowStrategy

STRATEGY_REGISTRY: dict[str, Type[BaseStrategy]] = {
    "趋势跟踪": TrendFollowStrategy,
    "均值回归": MeanRevertStrategy,
    "动量突破": MomentumStrategy,
    "多因子轮动": MultiFactorStrategy,
    "每日动量选股": DailyMomentumStrategy,
}


def get_strategy(name: str, params: dict = None) -> BaseStrategy:
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"未知策略: {name}")
    return STRATEGY_REGISTRY[name](params)
