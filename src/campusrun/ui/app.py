"""CampusRun 主窗口：侧边导航 + 四个页面 + 后台任务队列。"""

from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any, Callable

from .. import __version__
from ..config import AppPaths
from ..errors import CampusRunError
from ..service import CampusRunService
from .connection import ConnectionPage
from .dashboard import DashboardPage
from .help import HelpPage
from .plan_dialog import PlanDialog
from .records import RecordsPage
from .theme import (
    ACCENT,
    BG,
    PALETTE,
    configure_styles,
    enable_dpi_awareness,
    font,
)
from .widgets import NavItem, ScrollFrame, hline

LOG = logging.getLogger("campusrun.ui")


class CampusRunApp(tk.Tk):
    def __init__(self, service: CampusRunService):
        super().__init__()
        self.service = service
        self.plan = service.plan()
        self._events: queue.Queue[tuple[Callable[[Any], None], Any]] = queue.Queue()
        self._busy = False
        self._closing = False
        self._last_page = service.config.last_page or "dashboard"

        self.title("CampusRun · 校园乐跑")
        self.configure(bg=BG)
        # Tk 的字体按 DPI 缩放，但 geometry 用的是物理像素；
        # 因此窗口尺寸要按系统缩放倍率放大，否则 150% 缩放下内容会被裁掉。
        self.ui_scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        max_width = max(900, self.winfo_screenwidth() - 40)
        max_height = max(620, self.winfo_screenheight() - 80)
        min_width = min(int(1100 * self.ui_scale), max_width)
        min_height = min(int(700 * self.ui_scale), max_height)
        self.minsize(min_width, min_height)
        default_width = min(int(1180 * self.ui_scale), max_width)
        default_height = min(int(860 * self.ui_scale), max_height)
        geometry = service.config.window_geometry or f"{default_width}x{default_height}"
        try:
            self.geometry(geometry)
        except tk.TclError:
            self.geometry(f"{default_width}x{default_height}")
        try:
            self.iconname("CampusRun")
        except tk.TclError:
            pass

        configure_styles(self)
        self._build_sidebar()
        self._build_content()
        self._build_pages()
        self.show_page(self._last_page if self._last_page in self.pages else "dashboard")
        self._refresh_sidebar()

        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_events)
        self.after(350, self._auto_refresh)
        if service.startup_warnings:
            self.after(
                600,
                lambda: messagebox.showwarning(
                    "启动提示",
                    "\n\n".join(service.startup_warnings),
                    parent=self,
                ),
            )

    # ------------------------------------------------------------------
    def _build_sidebar(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        sidebar = tk.Frame(self, bg=PALETTE["sidebar"], width=int(228 * self.ui_scale))
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)
        self.sidebar = sidebar

        brand = tk.Frame(sidebar, bg=PALETTE["sidebar"])
        brand.pack(fill="x", padx=20, pady=(24, 20))
        row = tk.Frame(brand, bg=PALETTE["sidebar"])
        row.pack(fill="x")
        tk.Label(row, text="CampusRun", bg=PALETTE["sidebar"], fg="#FFFFFF", font=(font("h1")[0], 15, "bold"), anchor="w").pack(side="left")
        tk.Label(row, text="●", bg=PALETTE["sidebar"], fg=ACCENT, font=font("small")).pack(side="left", padx=(6, 0))
        tk.Label(
            brand,
            text="东北大学 · 校园乐跑",
            bg=PALETTE["sidebar"],
            fg=PALETTE["sidebar_text"],
            font=font("tiny"),
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        nav = tk.Frame(sidebar, bg=PALETTE["sidebar"])
        nav.pack(fill="x", pady=(4, 0))
        self.nav_items: dict[str, NavItem] = {}
        for key, label in (
            ("dashboard", "概览"),
            ("records", "跑步记录"),
            ("connection", "连接设置"),
            ("help", "抓包帮助"),
        ):
            item = NavItem(nav, key, label, self.show_page)
            item.pack(fill="x", pady=1)
            self.nav_items[key] = item

        tk.Frame(sidebar, bg=PALETTE["sidebar"]).pack(fill="both", expand=True)

        status = tk.Frame(sidebar, bg=PALETTE["sidebar"])
        status.pack(fill="x", padx=18, pady=(0, 12))
        hline(status, bg="#1E2A44")
        tk.Label(
            status,
            text="数据状态",
            bg=PALETTE["sidebar"],
            fg=PALETTE["sidebar_muted"],
            font=font("tiny"),
            anchor="w",
        ).pack(anchor="w", pady=(10, 3))
        self.sidebar_source = tk.Label(
            status,
            text="—",
            bg=PALETTE["sidebar"],
            fg="#E2E8F0",
            font=font("small"),
            anchor="w",
            justify="left",
            wraplength=190,
        )
        self.sidebar_source.pack(anchor="w")
        self.sidebar_hint = tk.Label(
            status,
            text="",
            bg=PALETTE["sidebar"],
            fg=PALETTE["sidebar_muted"],
            font=font("tiny"),
            anchor="w",
            justify="left",
            wraplength=190,
        )
        self.sidebar_hint.pack(anchor="w", pady=(4, 0))

        bottom = tk.Frame(sidebar, bg=PALETTE["sidebar"])
        bottom.pack(fill="x", padx=20, pady=(0, 16))
        tk.Label(
            bottom,
            text=f"v{__version__} · 只读工具",
            bg=PALETTE["sidebar"],
            fg=PALETTE["sidebar_muted"],
            font=font("tiny"),
            anchor="w",
        ).pack(anchor="w")

    def _build_content(self) -> None:
        self.content = tk.Frame(self, bg=BG)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

    def _build_pages(self) -> None:
        self.pages: dict[str, tk.Frame] = {
            "dashboard": DashboardPage(self.content, self),
            "records": RecordsPage(self.content, self),
            "connection": ConnectionPage(self.content, self),
            "help": HelpPage(self.content, self),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    # ------------------------------------------------------------------
    def show_page(self, name: str) -> None:
        page = self.pages.get(name)
        if page is None:
            return
        page.tkraise()
        self._last_page = name
        for key, item in self.nav_items.items():
            item.set_active(key == name)
        try:
            page.refresh()
        except Exception:  # noqa: BLE001 - 页面刷新失败不应让窗口崩掉
            LOG.exception("刷新页面失败：%s", name)

    def refresh_views(self) -> None:
        self.plan = self.service.plan()
        for name, page in self.pages.items():
            try:
                page.refresh()
            except Exception:  # noqa: BLE001
                LOG.exception("刷新页面失败：%s", name)
        self._refresh_sidebar()

    def _refresh_sidebar(self) -> None:
        source = self.service.source_text()
        self.sidebar_source.configure(text=source)
        if self.service.is_demo:
            self.sidebar_source.configure(fg="#93C5FD")
            self.sidebar_hint.configure(text="演示数据 · 不影响真实记录")
        elif self.service.summary is not None:
            self.sidebar_source.configure(fg="#86EFAC")
            age = self.service.summary.fetched_at.strftime("%m-%d %H:%M")
            self.sidebar_hint.configure(text=f"上次获取 {age}")
        else:
            self.sidebar_source.configure(fg="#FCD34D")
            self.sidebar_hint.configure(text="尚未获取数据")

    def set_status(self, text: str, tone: str = "muted") -> None:
        colors = {
            "success": "#86EFAC",
            "warn": "#FCD34D",
            "danger": "#FCA5A5",
            "accent": "#93C5FD",
            "muted": PALETTE["sidebar_muted"],
        }
        self.sidebar_hint.configure(text=text, fg=colors.get(tone, PALETTE["sidebar_muted"]))
        self.after(6000, lambda: self._restore_hint(text))

    def _restore_hint(self, text: str) -> None:
        if self._closing or self.sidebar_hint.cget("text") != text:
            return
        self._refresh_sidebar()

    # ------------------------------------------------------------------
    @property
    def busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        dashboard = self.pages.get("dashboard")
        if isinstance(dashboard, DashboardPage):
            dashboard.set_busy(busy)

    def update_settings(self, **changes: Any) -> None:
        self.service.update_config(**changes)
        self.plan = self.service.plan()
        self.refresh_views()
        self.set_status("设置已保存", "success")

    def set_demo_mode(self, enabled: bool) -> None:
        if enabled == self.service.is_demo:
            return
        if not enabled and not self.service.has_connection:
            messagebox.showinfo("还没有连接", "请先抓包并保存真实接口。", parent=self)
            return
        self.service.set_demo_mode(enabled)
        self.plan = self.service.plan()
        self.refresh_views()
        self.set_status("已切换为演示数据" if enabled else "已切换为真实数据", "accent")

    def refresh_data(self) -> None:
        if self._busy:
            return
        if not self.service.is_demo and not self.service.has_connection:
            messagebox.showinfo("还没有连接", "请先到“连接设置”粘贴抓包得到的 cURL。", parent=self)
            self.show_page("connection")
            return
        self._busy = True
        self.set_busy(True)
        self.set_status("正在获取数据…", "warn")
        self.run_async(self.service.refresh, self._on_refresh_ok, self._on_refresh_error)

    def _on_refresh_ok(self, summary) -> None:
        self._busy = False
        self.set_busy(False)
        self.plan = self.service.plan()
        self.refresh_views()
        self.set_status(f"已更新：{summary.completed_km:.1f} km / {summary.completed_runs} 次", "success")

    def _on_refresh_error(self, exc: Exception) -> None:
        self._busy = False
        self.set_busy(False)
        self.set_status("刷新失败，保留上次数据", "danger")
        self.show_error("刷新失败", str(exc))

    # ------------------------------------------------------------------
    def run_async(
        self,
        work: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        def worker() -> None:
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001 - 异常交回 UI 线程展示
                LOG.exception("后台任务失败")
                self._events.put((on_error, exc))
            else:
                self._events.put((on_success, result))

        threading.Thread(target=worker, name="campusrun-worker", daemon=True).start()

    def _drain_events(self) -> None:
        if self._closing:
            return
        try:
            while True:
                callback, value = self._events.get_nowait()
                try:
                    callback(value)
                except Exception:  # noqa: BLE001
                    LOG.exception("后台任务回调失败")
        except queue.Empty:
            pass
        finally:
            if not self._closing:
                self.after(80, self._drain_events)

    # ------------------------------------------------------------------
    def show_plan_dialog(self) -> None:
        PlanDialog(self, self)

    def export_csv(self) -> None:
        try:
            path = self.service.export_csv()
        except CampusRunError as exc:
            self.show_error("无法导出", str(exc))
            return
        self.set_status("已导出 CSV", "success")
        if messagebox.askyesno("导出成功", f"已导出到：\n{path}\n\n是否打开所在文件夹？", parent=self):
            try:
                os.startfile(str(path.parent))  # type: ignore[attr-defined]
            except OSError as exc:
                self.show_error("无法打开文件夹", str(exc))

    def show_error(self, title: str, message: str) -> None:
        LOG.warning("%s：%s", title, message)
        messagebox.showerror(title, message, parent=self)

    # ------------------------------------------------------------------
    def _auto_refresh(self) -> None:
        if self._closing:
            return
        if not self.service.is_demo:
            if self.service.has_connection:
                self.refresh_data()
            elif self.service.summary is None:
                self.show_page("connection")

    def _on_mousewheel(self, event: tk.Event) -> str | None:
        widget = self.winfo_containing(event.x_root, event.y_root)
        delta = -int(event.delta / 120) if getattr(event, "delta", 0) else 0
        if not delta:
            return None
        while widget is not None:
            if isinstance(widget, ScrollFrame):
                if widget.canvas.winfo_height() < widget.inner.winfo_reqheight():
                    widget.canvas.yview_scroll(delta, "units")
                    return "break"
                return None
            widget = getattr(widget, "master", None)
        return None

    def _on_close(self) -> None:
        self._closing = True
        try:
            self.service.config.window_geometry = self.geometry()
            self.service.config.last_page = self._last_page
            self.service.save_config()
        except Exception:  # noqa: BLE001
            LOG.exception("保存窗口状态失败")
        self.destroy()


def run_app(paths: AppPaths) -> int:
    enable_dpi_awareness()
    try:
        service = CampusRunService(paths)
    except CampusRunError as exc:
        print(f"启动失败：{exc}")
        return 1
    app: CampusRunApp | None = None
    try:
        app = CampusRunApp(service)
        app.mainloop()
        return 0
    except tk.TclError as exc:
        print(f"无法启动图形界面：{exc}")
        print("请确认当前会话有可用桌面，并且 Python 安装包含 tkinter。")
        return 1
    finally:
        if app is not None:
            try:
                app.destroy()
            except tk.TclError:
                pass
