"""统一的异常类型，便于 CLI 与 GUI 输出可读的中文提示。"""

from __future__ import annotations


class CampusRunError(Exception):
    """所有可预期错误的基类；消息可直接展示给用户。"""


class ConfigError(CampusRunError):
    """配置文件损坏或取值非法。"""


class SecretError(CampusRunError):
    """Windows DPAPI 加解密失败。"""


class CaptureParseError(CampusRunError):
    """粘贴的 cURL / HTTP 请求无法解析。"""


class ProviderError(CampusRunError):
    """网络请求失败、登录失效或返回体无法解析。"""


class MappingError(CampusRunError):
    """抓包字段映射无法从响应中取值。"""
