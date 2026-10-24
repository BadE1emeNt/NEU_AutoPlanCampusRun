"""首次使用的引导弹窗（只介绍账号登录、目标设置和结果查看）。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .theme import ACCENT, BG, BORDER, CARD, FAINT, MUTED, TEXT, font
from .widgets import Card


PAGES: list[tuple[str, str, list[str]]] = [
    (
        "欢迎使用 CampusRun",
        "这是东北大学“校园乐跑”的只读查询与配速规划工具。",
        [
            "读取本学期已跑次数、累计公里和逐条记录",
            "按目标公里数和截止日期，计算每天需要跑多少",
            "生成 2/3/4/5 km 的完成天数与逐日计划",
            "只读：不提交跑步、不修改成绩、不伪造轨迹",
        ],
    ),
    (
        "第一步：登录账号",
        "到左侧“连接设置 → ① 账号登录”，输入学号和统一身份认证密码。",
        [
            "如果学校要求短信二次认证，按弹窗输入验证码",
            "首次登录如要求绑定邮箱，可点“稍后绑定”跳过",
            "勾选“记住密码”可自动重登；密码用 Windows DPAPI 加密",
            "不想保存密码时不要勾选“记住密码”",
        ],
    ),
    (
        "第二步：设置目标",
        "回到“概览”，在“目标与截止”卡片里设置：",
        [
            "目标公里数：按学校本学期要求填写（默认 96 km）",
            "截止日期：格式 YYYY-MM-DD，可跑天数算到这一天",
            "每周休息日：勾选不跑步的星期",
            "单次有效里程 2–5 km；今天已跑则从明天开始算",
        ],
    ),
    (
        "第三步：查看规划",
        "概览会自动算出每天 2/3/4/5 km 分别需要几天，以及预计完成日期。",
        [
            "“查看完整计划”可以切换里程并复制日程",
            "“跑步记录”查看每次里程、用时和配速，可导出 CSV",
            "没有登录时可用演示模式先熟悉界面",
            "数据只保存在本机；不上传密码或 token",
        ],
    ),
]


class OnboardingDialog(tk.Toplevel):
    """模态使用指南；完成时回调 True，直接关闭时回调 False。"""

    def __init__(self, parent: tk.Misc, on_finish: Callable[[bool], None]):
        super().__init__(parent)
        self.parent = parent
        self._on_finish = on_finish
        self._finished = False
        self._index = 0

        self.title("使用指南 · CampusRun")
        self.configure(bg=BG)
        self.transient(parent)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _event: self._close())
        self.bind("<Right>", lambda _event: self._next())
        self.bind("<Left>", lambda _event: self._prev())

        self.ui_scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        width = min(int(760 * self.ui_scale), self.winfo_screenwidth() - 80)
        height = min(int(500 * self.ui_scale), self.winfo_screenheight() - 100)

        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True, padx=24, pady=20)

        header = tk.Frame(shell, bg=BG)
        header.pack(fill="x", pady=(0, 12))
        tk.Label(
            header,
            text="使用指南",
            bg=BG,
            fg=TEXT,
            font=font("h1"),
            anchor="w",
        ).pack(side="left")
        self.step_label = tk.Label(
            header,
            text="1 / 4",
            bg=BG,
            fg=ACCENT,
            font=font("small"),
            anchor="e",
        )
        self.step_label.pack(side="right")

        card = Card(shell, padding=24)
        card.pack(fill="both", expand=True)
        self.body = card.body

        self.pages: list[tk.Frame] = []
        for title, lead, bullets in PAGES:
            page = tk.Frame(self.body, bg=CARD)
            tk.Label(
                page,
                text=title,
                bg=CARD,
                fg=TEXT,
                font=font("h2"),
                anchor="w",
            ).pack(anchor="w")
            tk.Label(
                page,
                text=lead,
                bg=CARD,
                fg=MUTED,
                font=font("body"),
                anchor="w",
                justify="left",
                wraplength=int(620 * self.ui_scale),
            ).pack(anchor="w", pady=(8, 14))
            for text in bullets:
                row = tk.Frame(page, bg=CARD)
                row.pack(fill="x", anchor="w", pady=3)
                tk.Label(
                    row,
                    text="•",
                    bg=CARD,
                    fg=ACCENT,
                    font=font("body"),
                    anchor="n",
                ).pack(side="left", padx=(2, 8))
                tk.Label(
                    row,
                    text=text,
                    bg=CARD,
                    fg=TEXT,
                    font=font("body"),
                    anchor="w",
                    justify="left",
                    wraplength=int(580 * self.ui_scale),
                ).pack(side="left", fill="x", expand=True)
            self.pages.append(page)

        footer = tk.Frame(shell, bg=BG)
        footer.pack(fill="x", pady=(14, 0))
        self.back_btn = ttk.Button(
            footer,
            text="上一步",
            style="Ghost.TButton",
            command=self._prev,
        )
        self.back_btn.pack(side="left")
        self.close_btn = ttk.Button(
            footer,
            text="关闭",
            style="Ghost.TButton",
            command=self._close,
        )
        self.close_btn.pack(side="right")
        self.next_btn = ttk.Button(
            footer,
            text="下一步",
            style="Accent.TButton",
            command=self._next,
        )
        self.next_btn.pack(side="right", padx=(0, 8))

        self._show_page(0)
        self.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.grab_set()
        self.lift()
        self.focus_force()

    def _show_page(self, index: int) -> None:
        self._index = max(0, min(index, len(self.pages) - 1))
        for page in self.pages:
            page.pack_forget()
        self.pages[self._index].pack(fill="both", expand=True)
        self.step_label.configure(text=f"{self._index + 1} / {len(self.pages)}")
        self.back_btn.configure(state="normal" if self._index > 0 else "disabled")
        self.next_btn.configure(
            text="开始使用" if self._index == len(self.pages) - 1 else "下一步"
        )

    def _prev(self) -> None:
        if self._index > 0:
            self._show_page(self._index - 1)

    def _next(self) -> None:
        if self._index < len(self.pages) - 1:
            self._show_page(self._index + 1)
            return
        self._finish(True)

    def _finish(self, completed: bool) -> None:
        if self._finished:
            return
        self._finished = True
        try:
            self.grab_release()
        except tk.TclError:
            pass
        try:
            self._on_finish(completed)
        finally:
            self.destroy()

    def _close(self) -> None:
        self._finish(False)
