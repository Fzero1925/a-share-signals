from abc import ABC, abstractmethod

import pandas as pd


class BaseStrategy(ABC):
    def __init__(self, params: dict = None):
        self.params = params if params else self.get_default_params()
        self.name = self.__class__.__name__

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        pass

    @staticmethod
    @abstractmethod
    def get_default_params() -> dict:
        pass

    def get_param(self, key: str, default=None):
        return self.params.get(key, default)


class MultiStockStrategy(ABC):
    def __init__(self, params: dict = None):
        self.params = params if params else self.get_default_params()
        self.name = self.__class__.__name__

    @abstractmethod
    def generate_signals(self, stock_data: dict) -> dict:
        pass

    @staticmethod
    @abstractmethod
    def get_default_params() -> dict:
        pass

    def get_param(self, key: str, default=None):
        return self.params.get(key, default)
