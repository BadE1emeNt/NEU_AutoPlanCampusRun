"""Windows UAC 提权辅助。

GUI 启动时如果当前不是管理员，自动用 ShellExecuteW("runas") 重新拉起自己，
让配置、token、缓存写入不受用户目录 ACL/受限令牌影响。
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys

_SW_SHOWNORMAL = 1
_MB_OK = 0x00000000
_MB_ICONWARNING = 0x00000030


def is_admin() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def _relaunch_command() -> tuple[str, str]:
    executable = sys.executable
    if getattr(sys, "frozen", False):
        args = sys.argv[1:]
    else:
        # 源码运行：python -m campusrun ...
        args = ["-m", "campusrun", *sys.argv[1:]]
    return executable, subprocess.list2cmdline(args)


def _message(text: str, title: str) -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, _MB_OK | _MB_ICONWARNING)
    except Exception:  # noqa: BLE001
        pass


def ensure_elevated() -> bool:
    """返回 True 表示当前进程可以继续；False 表示已退出或用户取消。"""

    if sys.platform != "win32" or is_admin():
        return True
    if os.environ.get("CAMPUSRUN_NO_ELEVATE") == "1":
        return True

    executable, params = _relaunch_command()
    try:
        shell32 = ctypes.windll.shell32
        shell32.ShellExecuteW.restype = ctypes.c_void_p
        result = shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            params,
            os.getcwd(),
            _SW_SHOWNORMAL,
        )
        code = int(result) if result else 0
    except Exception as exc:  # noqa: BLE001
        _message(f"无法请求管理员权限：{exc}", "CampusRun")
        return False

    if code > 32:
        # 已成功拉起提权后的新进程，当前进程退出即可。
        return False
    if code == 5:
        _message(
            "已取消管理员权限。\n\n"
            "程序需要写入本机配置/登录缓存；如果不提权，刷新时可能提示权限不足。\n"
            "请重新启动并在 UAC 窗口选择“是”。",
            "CampusRun",
        )
    else:
        _message(f"请求管理员权限失败（错误码 {code}）。", "CampusRun")
    return False
