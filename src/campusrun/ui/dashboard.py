"""概览页：进度、每日建议、2/3/4/5 km 完成天数与最快安排。"""

from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from ..analysis import PlanResult, ceil_div
from ..errors import CampusRunError
from ..formatting import (
    fmt_date_short,
    fmt_km,
    fmt_km_compact,
    fmt_minutes,
    fmt_percent,
    fmt_signed_days,
    weekday_cn,
)
from .theme import (
    ACCENT,
    ACCENT_SOFT,
    BG,
    BORDER,
    CARD,
    CARD_ALT,
    DANGER,
    FAINT,
    MUTED,
    PALETTE,
    SUCCESS,
    TEXT,
    WARN,
    font,
)
from .widgets import Card, Pill, ProgressRing, ScrollFrame, StatCard, hline, section_title


class DashboardPage(tk.Frame):
    def __init__(self, master: tk.Misc, app):
        super().__init__(master, bg=BG)
        self.app = app
        self._syncing = False
        self._scenario_rows: list[tk.Widget] = []
        self._schedule_chips: list[tk.Widget] = []

        self.scroll = ScrollFrame(self, bg=BG)
        self.scroll.pack(fill="both", expand=True)
        root = self.scroll.inner

        self._build_header(root)
        self._build_banner(root)
        self._build_stats(root)
        self._build_middle(root)
        self._build_scenarios(root)
        self._build_schedule(root)
        self._build_tips(root)

    # ------------------------------------------------------------------
    def _build_header(self, parent: tk.Misc) -> None:
        header = tk.Frame(parent, bg=BG)
        header.pack(fill="x", padx=30, pady=(24, 12))
        left = tk.Frame(header, bg=BG)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="概览", bg=BG, fg=TEXT, font=font("h1"), anchor="w").pack(anchor="w")
        self.subtitle = tk.Label(left, text="", bg=BG, fg=MUTED, font=font("small"), anchor="w")
        self.subtitle.pack(anchor="w", pady=(5, 0))

        right = tk.Frame(header, bg=BG)
        right.pack(side="right", anchor="e")
        self.status_pill = Pill(right, "加载中", "muted")
        self.status_pill.pack(side="left", padx=(0, 10))
        self.refresh_btn = ttk.Button(
            right,
            text="刷新数据",
            style="Accent.TButton",
            command=self.app.refresh_data,
        )
        self.refresh_btn.pack(side="left")

    def _build_banner(self, parent: tk.Misc) -> None:
        self.banner = tk.Frame(parent, bg=ACCENT_SOFT, highlightthickness=1, highlightbackground="#D6E4FF")
        inner = tk.Frame(self.banner, bg=ACCENT_SOFT)
        inner.pack(fill="x", padx=16, pady=10)
        tk.Label(inner, text="●", bg=ACCENT_SOFT, fg=ACCENT, font=font("small")).pack(side="left")
        tk.Label(
            inner,
            text="当前展示的是演示数据，用来体验规划功能；连接真实账号后会自动替换。",
            bg=ACCENT_SOFT,
            fg=PALETTE["accent_dark"],
            font=font("small"),
        ).pack(side="left", padx=(8, 0))
        link = tk.Label(
            inner,
            text="去连接真实账号 →",
            bg=ACCENT_SOFT,
            fg=ACCENT,
            font=(font("small")[0], 9, "underline"),
            cursor="hand2",
        )
        link.pack(side="right")
        link.bind("<Button-1>", lambda _event: self.app.show_page("connection"))

    def _build_stats(self, parent: tk.Misc) -> None:
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", padx=24, pady=(4, 6))
        for column in range(4):
            frame.grid_columnconfigure(column, weight=1, uniform="stat")
        self.stat_done = StatCard(frame, "已完成里程", "—", "—")
        self.stat_remain = StatCard(frame, "剩余里程", "—", "—", accent=PALETTE["warn"])
        self.stat_daily = StatCard(frame, "每日摊平", "—", "—", accent=SUCCESS)
        self.stat_days = StatCard(frame, "可跑天数", "—", "—", accent=PALETTE["accent_dark"])
        for index, card in enumerate((self.stat_done, self.stat_remain, self.stat_daily, self.stat_days)):
            card.grid(row=0, column=index, sticky="nsew", padx=6)

    def _build_middle(self, parent: tk.Misc) -> None:
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", padx=24, pady=8)
        frame.grid_columnconfigure(0, weight=5, uniform="mid")
        frame.grid_columnconfigure(1, weight=4, uniform="mid")

        progress = Card(frame, padding=20)
        progress.grid(row=0, column=0, sticky="nsew", padx=(6, 6))
        top = tk.Frame(progress.body, bg=CARD)
        top.pack(fill="x")
        section_title(top, "本学期进度", "按有效记录累计，每天最多 1 次").pack(side="left")
        self.progress_pill = Pill(top, "", "accent")
        self.progress_pill.pack(side="right", anchor="n")

        content = tk.Frame(progress.body, bg=CARD)
        content.pack(fill="both", expand=True, pady=(14, 0))
        self.ring = ProgressRing(content, size=158, bg=CARD)
        self.ring.pack(side="left", padx=(0, 14))

        info = tk.Frame(content, bg=CARD)
        info.pack(side="left", fill="both", expand=True)
        tk.Label(info, text="还需完成", bg=CARD, fg=MUTED, font=font("small"), anchor="w").pack(anchor="w")
        self.remain_value = tk.Label(info, text="—", bg=CARD, fg=TEXT, font=font("stat_small"), anchor="w")
        self.remain_value.pack(anchor="w")
        self.finish_line = tk.Label(
            info,
            text="",
            bg=CARD,
            fg=PALETTE["success"],
            font=font("small"),
            anchor="w",
            justify="left",
            wraplength=235,
        )
        self.finish_line.pack(anchor="w", pady=(6, 8))
        self.progress_warning = tk.Label(
            info,
            text="",
            bg=CARD,
            fg=MUTED,
            font=font("small"),
            anchor="w",
            justify="left",
            wraplength=235,
        )
        self.progress_warning.pack(anchor="w")
        self.avg_line = tk.Label(
            info,
            text="",
            bg=CARD,
            fg=FAINT,
            font=font("tiny"),
            anchor="w",
            justify="left",
            wraplength=235,
        )
        self.avg_line.pack(anchor="w", pady=(10, 0))

        settings = Card(frame, padding=18)
        settings.grid(row=0, column=1, sticky="nsew", padx=(6, 6))
        section_title(settings.body, "目标与截止", "修改后自动保存").pack(anchor="w", pady=(0, 12))

        form = tk.Frame(settings.body, bg=CARD)
        form.pack(fill="x")
        for column in (0, 1):
            form.grid_columnconfigure(column, weight=1, uniform="set")

        self.target_var = tk.StringVar()
        self.deadline_var = tk.StringVar()
        self.pace_var = tk.StringVar()

        target_box = tk.Frame(form, bg=CARD)
        target_box.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        tk.Label(target_box, text="目标里程", bg=CARD, fg=MUTED, font=font("tiny"), anchor="w").pack(anchor="w")
        target_row = tk.Frame(target_box, bg=CARD)
        target_row.pack(anchor="w", fill="x", pady=(3, 0))
        self.target_spin = ttk.Spinbox(
            target_row,
            from_=1,
            to=1000,
            increment=1,
            width=7,
            textvariable=self.target_var,
            command=self._apply_settings,
            justify="right",
        )
        self.target_spin.pack(side="left")
        self.target_spin.bind("<FocusOut>", lambda _e: self._apply_settings())
        self.target_spin.bind("<Return>", lambda _e: self._apply_settings())
        tk.Label(target_row, text="km", bg=CARD, fg=MUTED, font=font("small")).pack(side="left", padx=(5, 0))

        deadline_box = tk.Frame(form, bg=CARD)
        deadline_box.grid(row=0, column=1, sticky="ew")
        tk.Label(deadline_box, text="截止日期", bg=CARD, fg=MUTED, font=font("tiny"), anchor="w").pack(anchor="w")
        self.deadline_entry = ttk.Entry(deadline_box, textvariable=self.deadline_var, width=12)
        self.deadline_entry.pack(anchor="w", fill="x", pady=(3, 0))
        self.deadline_entry.bind("<FocusOut>", lambda _e: self._apply_settings())
        self.deadline_entry.bind("<Return>", lambda _e: self._apply_settings())

        pace_box = tk.Frame(form, bg=CARD)
        pace_box.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(10, 0))
        tk.Label(pace_box, text="估算配速 (min/km)", bg=CARD, fg=MUTED, font=font("tiny"), anchor="w").pack(anchor="w")
        pace_row = tk.Frame(pace_box, bg=CARD)
        pace_row.pack(anchor="w", pady=(3, 0))
        self.pace_spin = ttk.Spinbox(
            pace_row,
            from_=3,
            to=10,
            increment=0.1,
            width=6,
            textvariable=self.pace_var,
            command=self._apply_settings,
            justify="right",
            format="%.1f",
        )
        self.pace_spin.pack(side="left")
        self.pace_spin.bind("<FocusOut>", lambda _e: self._apply_settings())
        self.pace_spin.bind("<Return>", lambda _e: self._apply_settings())

        rest_hint = tk.Frame(form, bg=CARD)
        rest_hint.grid(row=1, column=1, sticky="sw", pady=(10, 0))
        tk.Label(
            rest_hint,
            text="每天最多计 1 次\n单次有效 2–5 km",
            bg=CARD,
            fg=FAINT,
            font=font("tiny"),
            anchor="w",
            justify="left",
        ).pack(anchor="w")

        tk.Label(form, text="每周休息", bg=CARD, fg=MUTED, font=font("tiny"), anchor="w").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(14, 2)
        )
        rest_box = tk.Frame(form, bg=CARD)
        rest_box.grid(row=3, column=0, columnspan=2, sticky="w")
        self.rest_vars: list[tk.BooleanVar] = []
        for names in (("一", "二", "三", "四"), ("五", "六", "日")):
            line = tk.Frame(rest_box, bg=CARD)
            line.pack(anchor="w")
            for name in names:
                var = tk.BooleanVar(value=False)
                self.rest_vars.append(var)
                check = tk.Checkbutton(
                    line,
                    text=name,
                    variable=var,
                    command=self._apply_settings,
                    bg=CARD,
                    fg=TEXT,
                    activebackground=CARD,
                    activeforeground=TEXT,
                    selectcolor="#FFFFFF",
                    highlightthickness=0,
                    bd=0,
                    font=font("tiny"),
                    padx=0,
                    pady=1,
                    anchor="w",
                )
                check.pack(side="left", padx=(0, 10))

        self.settings_hint = tk.Label(
            settings.body,
            text=" ",
            bg=CARD,
            fg=SUCCESS,
            font=font("tiny"),
            anchor="w",
            justify="left",
            wraplength=300,
        )
        self.settings_hint.pack(anchor="w", pady=(8, 0))

    def _build_scenarios(self, parent: tk.Misc) -> None:
        card = Card(parent, padding=20)
        card.pack(fill="x", padx=30, pady=8)
        head = tk.Frame(card.body, bg=CARD)
        head.pack(fill="x")
        section_title(head, "每天跑多少，几天完成", "按剩余里程计算；每天最多 1 条有效记录").pack(side="left")

        self.scenario_box = tk.Frame(card.body, bg=CARD)
        self.scenario_box.pack(fill="x", pady=(14, 0))

        calc = tk.Frame(card.body, bg=CARD_ALT, highlightthickness=1, highlightbackground=BORDER)
        calc.pack(fill="x", pady=(14, 0))
        inner = tk.Frame(calc, bg=CARD_ALT)
        inner.pack(fill="x", padx=14, pady=10)
        controls = tk.Frame(inner, bg=CARD_ALT)
        controls.pack(fill="x")
        tk.Label(controls, text="自定义：每天跑", bg=CARD_ALT, fg=MUTED, font=font("small")).pack(side="left")
        self.custom_var = tk.StringVar(value="3.5")
        custom_entry = ttk.Entry(controls, textvariable=self.custom_var, width=6, justify="right")
        custom_entry.pack(side="left", padx=(8, 4))
        tk.Label(controls, text="km", bg=CARD_ALT, fg=MUTED, font=font("small")).pack(side="left")
        ttk.Button(controls, text="计算", command=self._calc_custom).pack(side="left", padx=(12, 0))
        self.custom_result = tk.Label(
            inner,
            text="输入任意每日里程，查看需要几天。",
            bg=CARD_ALT,
            fg=MUTED,
            font=font("small"),
            anchor="w",
            justify="left",
            wraplength=820,
        )
        self.custom_result.pack(anchor="w", fill="x", pady=(7, 0))
        custom_entry.bind("<Return>", lambda _e: self._calc_custom())

    def _build_schedule(self, parent: tk.Misc) -> None:
        card = Card(parent, padding=20)
        card.pack(fill="x", padx=30, pady=8)
        head = tk.Frame(card.body, bg=CARD)
        head.pack(fill="x")
        section_title(head, "最快完成安排", "按每次 5 km 上限、每天 1 次；可查看完整计划并复制").pack(side="left")
        actions = tk.Frame(head, bg=CARD)
        actions.pack(side="right", anchor="n")
        ttk.Button(actions, text="查看完整计划", command=self.app.show_plan_dialog).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="复制计划", command=self._copy_schedule).pack(side="left")

        self.schedule_box = tk.Frame(card.body, bg=CARD)
        self.schedule_box.pack(fill="x", pady=(14, 0))
        self.schedule_note = tk.Label(
            card.body,
            text="",
            bg=CARD,
            fg=FAINT,
            font=font("tiny"),
            anchor="w",
            justify="left",
            wraplength=900,
        )
        self.schedule_note.pack(anchor="w", pady=(6, 0))

    def _build_tips(self, parent: tk.Misc) -> None:
        self.tips_card = Card(parent, padding=18)
        self.tips_card.pack(fill="x", padx=30, pady=(8, 26))
        section_title(self.tips_card.body, "提示", "").pack(anchor="w", pady=(0, 8))
        self.tips_label = tk.Label(
            self.tips_card.body,
            text="",
            bg=CARD,
            fg=MUTED,
            font=font("small"),
            anchor="w",
            justify="left",
            wraplength=980,
        )
        self.tips_label.pack(anchor="w")

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        plan = self.app.plan
        self.subtitle.configure(
            text=(
                f"{plan.today.year}年{plan.today.month}月{plan.today.day}日 {weekday_cn(plan.today)}"
                f"  ·  距截止 {plan.calendar_days_left} 天"
                f"  ·  数据来源：{self.app.service.source_text()}"
            )
        )
        self.status_pill.set(f"{plan.status.label}", plan.status.tone)
        self.refresh_btn.configure(state="disabled" if self.app.busy else "normal")

        self.banner.pack_forget()
        if self.app.service.is_demo:
            self.banner.pack(fill="x", padx=30, pady=(0, 10), before=self.stat_done.master)

        self.stat_done.set(fmt_km(plan.completed_km), f"{plan.completed_runs} 次有效记录")
        self.stat_remain.set(fmt_km(plan.remaining_km), f"目标 {plan.target_km:g} km")
        if plan.remaining_km <= 0:
            self.stat_remain.set("0 km", "目标已达成", tone="success")
        if plan.available_days:
            self.stat_daily.set(
                f"{plan.required_per_day_km:.2f} km",
                f"按 {plan.available_days} 个可跑日摊平",
            )
        else:
            self.stat_daily.set("—", "没有可跑日", tone="danger")
        self.stat_days.set(f"{plan.available_days} 天", f"截止 {plan.deadline.isoformat()}")

        tone = plan.status.tone
        ring_color = {
            "success": SUCCESS,
            "ok": ACCENT,
            "warn": WARN,
            "danger": DANGER,
        }.get(tone, ACCENT)
        self.ring.set(plan.progress_ratio, fmt_percent(plan.progress_ratio), "完成度", ring_color)
        self.progress_pill.set(plan.status.label, tone)

        if plan.remaining_km <= 0:
            self.remain_value.configure(text="已完成")
            self.finish_line.configure(text="本学期目标已经达成，保持节奏即可。", fg=SUCCESS)
        else:
            self.remain_value.configure(text=f"{plan.remaining_km:.1f} km")
            if plan.earliest_finish:
                self.finish_line.configure(
                    text=(
                        f"最快 {plan.min_days} 天 · {fmt_date_short(plan.earliest_finish)} 完成"
                        f" · 余 {plan.slack_days} 天"
                    ),
                    fg=SUCCESS if plan.feasible else DANGER,
                )
            else:
                self.finish_line.configure(text="按当前目标与截止日，已无法完成。", fg=DANGER)

        if plan.warnings:
            self.progress_warning.configure(text="\n".join(f"· {w}" for w in plan.warnings[:2]))
        else:
            self.progress_warning.configure(text="")
        if plan.completed_runs:
            self.avg_line.configure(
                text=f"平均每次 {plan.completed_km / plan.completed_runs:.2f} km · 记录 {plan.completed_runs} 次"
            )
        else:
            self.avg_line.configure(text="暂无有效记录")

        self._sync_settings(plan)
        self._render_scenarios(plan)
        self._render_schedule(plan)
        self._render_tips(plan)
        self._calc_custom(silent=True)

    def _sync_settings(self, plan: PlanResult) -> None:
        config = self.app.service.config
        focus = self.focus_get()
        self._syncing = True
        try:
            if focus not in (self.target_spin, self.deadline_entry, self.pace_spin):
                self.target_var.set(f"{config.target_km:g}")
                self.deadline_var.set(config.deadline.isoformat())
                self.pace_var.set(f"{config.pace_min_per_km:g}")
            for index, var in enumerate(self.rest_vars):
                var.set(index in config.rest_weekdays)
        finally:
            self._syncing = False

    def _apply_settings(self) -> None:
        if self._syncing:
            return
        try:
            target = float(self.target_var.get().strip().replace(",", "."))
            deadline = date.fromisoformat(self.deadline_var.get().strip())
            pace = float(self.pace_var.get().strip().replace(",", "."))
            rest = [index for index, var in enumerate(self.rest_vars) if var.get()]
        except ValueError:
            self.settings_hint.configure(text="日期格式 YYYY-MM-DD，数字请填写有效值。", fg=DANGER)
            return
        try:
            self.app.update_settings(
                target_km=target,
                deadline=deadline,
                pace_min_per_km=pace,
                rest_weekdays=rest,
            )
        except (CampusRunError, ValueError) as exc:
            self.settings_hint.configure(text=str(exc), fg=DANGER)
            return
        self.settings_hint.configure(text="已自动保存", fg=SUCCESS)

    def _render_scenarios(self, plan: PlanResult) -> None:
        for widget in self.scenario_box.winfo_children():
            widget.destroy()

        headers = ("每天跑", "需要天数", "完成日期", "余量", "状态")
        header = tk.Frame(self.scenario_box, bg=CARD_ALT)
        header.pack(fill="x")
        for index, text in enumerate(headers):
            header.grid_columnconfigure(index, weight=1)
            tk.Label(
                header,
                text=text,
                bg=CARD_ALT,
                fg=MUTED,
                font=font("tiny"),
                anchor="w" if index == 0 else "center",
            ).grid(row=0, column=index, sticky="ew", padx=10, pady=7)

        for row_index, scenario in enumerate(plan.scenarios):
            hline(self.scenario_box)
            row = tk.Frame(self.scenario_box, bg=CARD)
            row.pack(fill="x")
            for index in range(len(headers)):
                row.grid_columnconfigure(index, weight=1)
            finish = fmt_date_short(scenario.finish) if scenario.finish else "—"
            slack = fmt_signed_days(scenario.slack_days) if scenario.slack_days is not None else "—"
            if scenario.days == 0:
                status_text, status_fg = "已完成", SUCCESS
            elif scenario.feasible:
                status_text, status_fg = "可行", SUCCESS
            else:
                status_text, status_fg = "来不及", DANGER
            values = (
                fmt_km_compact(scenario.per_day_km),
                f"{scenario.days} 天" if scenario.days else "—",
                finish,
                slack,
                status_text,
            )
            for index, value in enumerate(values):
                fg = status_fg if index == 4 else (TEXT if index == 0 else MUTED)
                weight = "bold" if index == 0 else "normal"
                tk.Label(
                    row,
                    text=value,
                    bg=CARD,
                    fg=fg,
                    font=(font("small")[0], 9, weight),
                    anchor="w" if index == 0 else "center",
                ).grid(row=0, column=index, sticky="ew", padx=10, pady=8)

    def _render_schedule(self, plan: PlanResult) -> None:
        for widget in self.schedule_box.winfo_children():
            widget.destroy()
        if plan.remaining_km <= 0:
            tk.Label(
                self.schedule_box,
                text="目标已完成，不需要额外安排。",
                bg=CARD,
                fg=SUCCESS,
                font=font("small"),
                anchor="w",
            ).pack(anchor="w")
            self.schedule_note.configure(text="")
            return
        if not plan.schedule:
            tk.Label(
                self.schedule_box,
                text="按当前可跑日无法完成；请放宽截止日、降低目标或取消部分休息日。",
                bg=CARD,
                fg=DANGER,
                font=font("small"),
                anchor="w",
            ).pack(anchor="w")
            self.schedule_note.configure(text="")
            return

        grid = tk.Frame(self.schedule_box, bg=CARD)
        grid.pack(fill="x")
        for column in range(3):
            grid.grid_columnconfigure(column, weight=1, uniform="sched")
        for index, run in enumerate(plan.schedule[:6]):
            chip = tk.Frame(grid, bg=CARD_ALT, highlightthickness=1, highlightbackground=BORDER)
            chip.grid(row=index // 3, column=index % 3, sticky="nsew", padx=4, pady=4)
            date_text = f"{run.day.month}月{run.day.day}日 {run.weekday}"
            tk.Label(chip, text=date_text, bg=CARD_ALT, fg=MUTED, font=font("tiny"), anchor="w").pack(
                anchor="w", padx=10, pady=(7, 0)
            )
            detail = tk.Label(
                chip,
                text=f"{run.km:.2f} km · 约 {fmt_minutes(run.minutes)}",
                bg=CARD_ALT,
                fg=TEXT,
                font=(font("small")[0], 10, "bold"),
                anchor="w",
            )
            detail.pack(anchor="w", padx=10, pady=(1, 7))
            chip.bind("<Button-1>", lambda _e: self.app.show_plan_dialog())

        suffix = f"；另有 {len(plan.schedule) - 6} 次，点“查看完整计划”" if len(plan.schedule) > 6 else ""
        self.schedule_note.configure(
            text=(
                f"共 {len(plan.schedule)} 次，合计 {sum(r.km for r in plan.schedule):.1f} km，"
                f"{plan.schedule[-1].day.isoformat()} 完成{suffix}。"
            )
        )

    def _render_tips(self, plan: PlanResult) -> None:
        if not plan.warnings:
            self.tips_card.pack_forget()
            return
        self.tips_card.pack(fill="x", padx=30, pady=(8, 26))
        self.tips_label.configure(text="\n".join(f"· {warning}" for warning in plan.warnings))

    def _calc_custom(self, silent: bool = False) -> None:
        plan = self.app.plan
        raw = self.custom_var.get().strip().replace(",", ".")
        try:
            per_day = float(raw)
        except ValueError:
            if not silent:
                self.custom_result.configure(text="请输入有效数字。", fg=DANGER)
            return
        if per_day <= 0 or per_day > 50:
            if not silent:
                self.custom_result.configure(text="每日里程应在 0–50 km 之间。", fg=DANGER)
            return
        min_run = self.app.service.config.min_run_km
        max_run = self.app.service.config.max_run_km
        note = ""
        if per_day < min_run:
            note = f"单次有效记录至少 {min_run:g} km，按 {min_run:g} km 计算："
            per_day = min_run
        elif per_day > max_run:
            note = f"单次有效记录最多 {max_run:g} km，按 {max_run:g} km 计算："
            per_day = max_run
        if plan.remaining_km <= 0:
            self.custom_result.configure(text="目标已完成。", fg=SUCCESS)
            return
        days = ceil_div(plan.remaining_km, per_day)
        if days <= len(plan.available_dates):
            finish = plan.available_dates[days - 1]
            slack = len(plan.available_dates) - days
            text = (
                f"{note}每天 {per_day:g} km → {days} 天，{fmt_date_short(finish)} 完成"
                f"（{fmt_signed_days(slack)}）"
            )
            self.custom_result.configure(text=text, fg=TEXT)
        else:
            self.custom_result.configure(
                text=(
                    f"{note}每天 {per_day:g} km → 需要 {days} 天，"
                    f"但只剩 {len(plan.available_dates)} 个可跑日，来不及。"
                ),
                fg=DANGER,
            )

    def _copy_schedule(self) -> None:
        plan = self.app.plan
        if not plan.schedule:
            messagebox.showinfo("没有可复制的计划", "当前无法生成可行的跑步计划。", parent=self.app)
            return
        lines = [
            f"CampusRun 跑步计划（{plan.schedule[0].km:.1f} km/次，共 {len(plan.schedule)} 次）",
            f"目标 {plan.target_km:g} km · 截止 {plan.deadline.isoformat()}",
            "",
        ]
        for run in plan.schedule:
            lines.append(f"{run.day.isoformat()} {run.weekday}  {run.km:.2f} km  约 {fmt_minutes(run.minutes)}")
        self.app.clipboard_clear()
        self.app.clipboard_append("\n".join(lines))
        self.app.set_status("计划已复制到剪贴板", "success")

    def set_busy(self, busy: bool) -> None:
        self.refresh_btn.configure(state="disabled" if busy else "normal")
