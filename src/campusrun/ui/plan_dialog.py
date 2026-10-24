"""完整计划弹窗：按 2/3/4/5 km 或自定义每日里程生成逐日安排。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..analysis import schedule_for
from ..formatting import fmt_date_week, fmt_km, fmt_minutes, fmt_signed_days
from .theme import BG, BORDER, CARD, FAINT, MUTED, SUCCESS, TEXT, font
from .widgets import hline


class PlanDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.plan = app.plan
        self.settings = app.service.config.to_plan_settings()
        self.per_day = float(self.plan.scenarios[-1].per_day_km) if self.plan.scenarios else 5.0
        self.title("CampusRun · 完整跑步计划")
        self.transient(master)
        self.resizable(True, True)
        self.ui_scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self.minsize(int(620 * self.ui_scale), int(520 * self.ui_scale))
        self.geometry(f"{int(680 * self.ui_scale)}x{int(620 * self.ui_scale)}")
        self._center()
        self._build()
        self._render()
        self.grab_set()
        self.bind("<Escape>", lambda _event: self._close())

    def _center(self) -> None:
        self.update_idletasks()
        width = int(680 * self.ui_scale)
        height = int(620 * self.ui_scale)
        parent = self.master
        x = max(0, parent.winfo_rootx() + (parent.winfo_width() - width) // 2)
        y = max(0, parent.winfo_rooty() + (parent.winfo_height() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build(self) -> None:
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=22, pady=(20, 8))
        tk.Label(header, text="完整跑步计划", bg=BG, fg=TEXT, font=font("h1"), anchor="w").pack(anchor="w")
        tk.Label(
            header,
            text="每天最多 1 次有效记录；最后一天可少于所选里程，但不少于单次下限。",
            bg=BG,
            fg=MUTED,
            font=font("small"),
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        card = tk.Frame(self, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=22, pady=8)
        body = tk.Frame(card, bg=CARD)
        body.pack(fill="both", expand=True, padx=16, pady=14)

        controls = tk.Frame(body, bg=CARD)
        controls.pack(fill="x")
        tk.Label(controls, text="每天跑", bg=CARD, fg=MUTED, font=font("small")).pack(side="left")
        self.option_buttons: dict[float, ttk.Button] = {}
        for option in self.settings.daily_options:
            button = ttk.Button(
                controls,
                text=f"{option:g} km",
                command=lambda value=float(option): self._select(value),
            )
            button.pack(side="left", padx=(8, 0))
            self.option_buttons[float(option)] = button

        custom_row = tk.Frame(body, bg=CARD)
        custom_row.pack(fill="x", pady=(8, 0))
        tk.Label(custom_row, text="自定义", bg=CARD, fg=MUTED, font=font("small")).pack(side="left")
        self.custom_var = tk.StringVar(value=f"{self.per_day:g}")
        entry = ttk.Entry(custom_row, textvariable=self.custom_var, width=5, justify="right")
        entry.pack(side="left", padx=(8, 4))
        entry.bind("<Return>", lambda _event: self._apply_custom())
        tk.Label(custom_row, text="km", bg=CARD, fg=MUTED, font=font("small")).pack(side="left")
        ttk.Button(custom_row, text="应用", command=self._apply_custom).pack(side="left", padx=(10, 0))
        tk.Label(
            custom_row,
            text=f"单次有效 {self.settings.min_run_km:g}–{self.settings.max_run_km:g} km",
            bg=CARD,
            fg=FAINT,
            font=font("tiny"),
        ).pack(side="left", padx=(12, 0))

        hline(body)
        self.summary = tk.Label(
            body,
            text="",
            bg=CARD,
            fg=TEXT,
            font=font("small"),
            anchor="w",
            justify="left",
            wraplength=560,
        )
        self.summary.pack(fill="x", pady=10)

        table_wrap = tk.Frame(body, bg=CARD)
        table_wrap.pack(fill="both", expand=True)
        columns = ("date", "weekday", "km", "minutes")
        self.tree = ttk.Treeview(table_wrap, columns=columns, show="headings", height=12)
        for column, title, width, anchor in (
            ("date", "日期", 170, "w"),
            ("weekday", "星期", 100, "center"),
            ("km", "里程", 120, "center"),
            ("minutes", "预计用时", 150, "center"),
        ):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor=anchor, stretch=True)
        scrollbar = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        footer = tk.Frame(self, bg=BG)
        footer.pack(fill="x", padx=22, pady=(4, 18))
        ttk.Button(footer, text="复制计划", command=self._copy).pack(side="left")
        ttk.Button(footer, text="关闭", command=self._close).pack(side="right")

    def _select(self, value: float) -> None:
        self.per_day = value
        self.custom_var.set(f"{value:g}")
        self._render()

    def _apply_custom(self) -> None:
        try:
            value = float(self.custom_var.get().strip().replace(",", "."))
        except ValueError:
            messagebox.showinfo("无效数字", "请输入 1–5 之间的数字。", parent=self)
            return
        if not (self.settings.min_run_km <= value <= self.settings.max_run_km):
            messagebox.showinfo(
                "超出范围",
                f"单次有效里程为 {self.settings.min_run_km:g}–{self.settings.max_run_km:g} km。",
                parent=self,
            )
            return
        self.per_day = value
        self._render()

    def _render(self) -> None:
        for button in self.option_buttons.values():
            button.configure(style="TButton")
        selected = self.option_buttons.get(self.per_day)
        if selected is not None:
            selected.configure(style="Accent.TButton")

        for item in self.tree.get_children():
            self.tree.delete(item)

        plan = self.plan
        if plan.remaining_km <= 0:
            self.summary.configure(text="目标已完成，不需要额外安排。", fg=SUCCESS)
            return
        runs = schedule_for(plan.remaining_km, plan.available_dates, self.per_day, self.settings)
        if not runs:
            need_days = max(1, int(-(-plan.remaining_km // self.per_day)))
            self.summary.configure(
                text=(
                    f"按每天 {self.per_day:g} km，需要 {need_days} 天，但截止前只剩 "
                    f"{len(plan.available_dates)} 个可跑日，无法完成。"
                ),
                fg="#B42318",
            )
            return
        for run in runs:
            self.tree.insert(
                "",
                "end",
                values=(
                    run.day.isoformat(),
                    run.weekday,
                    f"{run.km:.2f} km",
                    fmt_minutes(run.minutes),
                ),
            )
        total = sum(run.km for run in runs)
        self.summary.configure(
            text=(
                f"每天约 {total / len(runs):.2f} km · 共 {len(runs)} 次 · 合计 {total:.1f} km · "
                f"{fmt_date_week(runs[-1].day)} 完成"
                f"（{fmt_signed_days(len(plan.available_dates) - len(runs))}）。"
            ),
            fg=TEXT,
        )

    def _copy(self) -> None:
        runs = self.tree.get_children()
        if not runs:
            messagebox.showinfo("没有计划", "当前参数下没有可复制的安排。", parent=self)
            return
        lines = [
            f"CampusRun 跑步计划（每天约 {self.per_day:g} km）",
            f"目标 {fmt_km(self.plan.target_km)} · 截止 {self.plan.deadline.isoformat()}",
            "",
        ]
        for item in runs:
            values = self.tree.item(item, "values")
            lines.append(f"{values[0]} {values[1]}  {values[2]}  约 {values[3]}")
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.app.set_status("计划已复制到剪贴板", "success")
        messagebox.showinfo("已复制", "完整计划已复制到剪贴板。", parent=self)

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
