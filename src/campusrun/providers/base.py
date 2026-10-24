"""数据来源抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import RunSummary


class Provider(ABC):
    name = "未命名数据源"
    is_demo = False

    @abstractmethod
    def fetch(self) -> RunSummary:
        """获取当前学期进度；失败时抛出 ProviderError。"""
