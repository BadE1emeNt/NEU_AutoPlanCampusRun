"""Windows DPAPI 封装：用当前 Windows 账户加密抓包凭据。

* 只有同一台机器、同一个 Windows 用户能解密；
* 不依赖第三方库；非 Windows 环境会抛出 SecretError，由上层决定降级策略。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from .errors import SecretError

_windows = sys.platform.startswith("win")
_ENTROPY = b"CampusRun.credentials.v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _make_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, max(1, len(data)))
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def _crypt32():
    try:
        return ctypes.WinDLL("crypt32", use_last_error=True)
    except (AttributeError, OSError) as exc:  # pragma: no cover - 非 Windows
        raise SecretError("当前环境没有 Windows 凭据加密接口（crypt32）") from exc


def _kernel32():
    try:
        return ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError) as exc:  # pragma: no cover
        raise SecretError("当前环境没有 Windows 内核接口（kernel32）") from exc


def protect_bytes(data: bytes) -> bytes:
    if not _windows:
        raise SecretError("DPAPI 仅在 Windows 上可用")
    if not data:
        return b""

    crypt32 = _crypt32()
    kernel32 = _kernel32()
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    input_blob, input_buffer = _make_blob(data)
    entropy_blob, entropy_buffer = _make_blob(_ENTROPY)
    output_blob = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "CampusRun",
        ctypes.byref(entropy_blob),
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    )
    _ = (input_buffer, entropy_buffer)
    if not ok:
        code = ctypes.get_last_error()
        raise SecretError(f"Windows 凭据加密失败（Win32 {code}）")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))


def unprotect_bytes(data: bytes) -> bytes:
    if not _windows:
        raise SecretError("DPAPI 仅在 Windows 上可用")
    if not data:
        return b""

    crypt32 = _crypt32()
    kernel32 = _kernel32()
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    input_blob, input_buffer = _make_blob(data)
    entropy_blob, entropy_buffer = _make_blob(_ENTROPY)
    output_blob = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    )
    _ = (input_buffer, entropy_buffer)
    if not ok:
        code = ctypes.get_last_error()
        raise SecretError(
            f"Windows 凭据解密失败（Win32 {code}）。"
            "连接文件可能来自其他 Windows 账户或机器，请重新粘贴 cURL。"
        )
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))


def available() -> bool:
    """轻量探测 DPAPI 是否可用（成功加密 1 字节即视为可用）。"""

    try:
        return unprotect_bytes(protect_bytes(b"ping")) == b"ping"
    except SecretError:
        return False
