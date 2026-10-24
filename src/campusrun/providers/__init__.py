"""数据源实现。"""

from __future__ import annotations

from .autodetect import Detection, describe_result, detect, summary_from_payload
from .base import Provider
from .http import HttpProvider
from .mock import MockProvider

__all__ = [
    "Detection",
    "HttpProvider",
    "MockProvider",
    "Provider",
    "describe_result",
    "detect",
    "summary_from_payload",
]
