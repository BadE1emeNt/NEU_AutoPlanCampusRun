"""跑步记录页。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..formatting import fmt_date_week, fmt_duration, fmt_km, fmt_pace
from .theme import BG, CARD, FAINT, MUTED, TEXT, font
from .widgets import Card


class RecordsPage(tk.Frame):
    def __init__(self, master: tk.Misc, app):
        super().__init__(master, bg=BG)
        self.app = app
        self._build()

    def _build(self) -> None:
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=30, pady=(24, 12))
        left = tk.Frame(header, bg=BG)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="跑步记录", bg=BG, fg=TEXT, font=font("h1"), anchor="w").pack(anchor="w")
        self.subtitle = tk.Label(left, text="按日期倒序显示，同一天有多条时按学校规则只计最远一次", bg=BG, fg=MUTED, font=font("small"), anchor="w")
        self.subtitle.pack(anchor="w", pady=(5, 0))
        actions = tk.Frame(header, bg=BG)
        actions.pack(side="right", anchor="e")
        ttk.Button(actions, text="刷新", command=self.app.refresh_data).pack(side="left", padx=(0, 8))
        self.export_btn = ttk.Button(actions, text="导出 CSV", style="Accent.TButton", command=self.app.export_csv)
        self.export_btn.pack(side="left")

        summary = Card(self, padding=0)
        summary.pack(fill="x", padx=30, pady=(0, 12))
        inner = tk.Frame(summary.body, bg=CARD)
        inner.pack(fill="x", padx=18, pady=14)
        for column in range(4):
            inner.grid_columnconfigure(column, weight=1, uniform="rec")
        self._summary_labels: dict[str, tk.Label] = {}
        specs = (
            ("runs", "有效次数"),
            ("km", "累计里程"),
            ("last", "最近一次"),
            ("source", "数据来源"),
        )
        for index, (key, title) in enumerate(specs):
            box = tk.Frame(inner, bg=CARD)
            box.grid(row=0, column=index, sticky="w", padx=8)
            tk.Label(box, text=title, bg=CARD, fg=MUTED, font=font("tiny"), anchor="w").pack(anchor="w")
            value = tk.Label(box, text="—", bg=CARD, fg=TEXT, font=(font("body")[0], 13, "bold"), anchor="w")
            value.pack(anchor="w", pady=(3, 0))
            self._summary_labels[key] = value

        table_card = Card(self, padding=10)
        table_card.pack(fill="both", expand=True, padx=30, pady=(0, 26))
        self.table_card = table_card
        table_wrap = tk.Frame(table_card.body, bg=CARD)
        table_wrap.pack(fill="both", expand=True)

        columns = ("date", "weekday", "km", "duration", "pace", "valid")
        self.tree = ttk.Treeview(
            table_wrap,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=14,
        )
        headings = {
            "date": "日期",
            "weekday": "星期",
            "km": "里程",
            "duration": "用时",
            "pace": "配速",
            "valid": "状态",
        }
        widths = {"date": 130, "weekday": 80, "km": 110, "duration": 110, "pace": 130, "valid": 100}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=widths[column],
                minwidth=60,
                anchor="w" if column == "date" else "center",
                stretch=True,
            )
        scrollbar = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.tag_configure("odd", background="#FBFCFF")
        self.tree.tag_configure("even", background=CARD)
        self.tree.tag_configure("invalid", foreground=FAINT)

        self.empty_label = tk.Label(
            table_card.body,
            text="",
            bg=CARD,
            fg=MUTED,
            font=font("small"),
            justify="center",
        )
        self.note = tk.Label(
            table_card.body,
            text="",
            bg=CARD,
            fg=FAINT,
            font=font("tiny"),
            anchor="w",
            justify="left",
            wraplength=980,
        )
        self.note.pack(side="bottom", fill="x", pady=(8, 0))

    def refresh(self) -> None:
        summary = self.app.service.summary
        if summary is None:
            self._summary_labels["runs"].configure(text="—")
            self._summary_labels["km"].configure(text="—")
            self._summary_labels["last"].configure(text="—")
            self._summary_labels["source"].configure(text=self.app.service.source_text())
            self._clear_tree()
            self._show_empty("还没有数据。请到“连接”页抓包，或开启演示数据。")
            self.export_btn.configure(state="disabled")
            self.note.configure(text="")
            return

        self._summary_labels["runs"].configure(text=f"{summary.completed_runs} 次")
        self._summary_labels["km"].configure(text=fmt_km(summary.completed_km))
        last = summary.last_day
        self._summary_labels["last"].configure(text=last.isoformat() if last else "—")
        self._summary_labels["source"].configure(text=summary.provider)
        self.export_btn.configure(state="normal" if summary.records else "disabled")

        self._clear_tree()
        records = sorted(summary.records, key=lambda item: item.day, reverse=True)
        if not records:
            if summary.aggregate_km is not None:
                self._show_empty("接口只返回了汇总数据，没有逐条记录；规划功能不受影响。")
            else:
                self._show_empty("暂无跑步记录。")
        else:
            self._hide_empty()
            for index, record in enumerate(records):
                tags = ["odd" if index % 2 else "even"]
                if not record.valid:
                    tags.append("invalid")
                self.tree.insert(
                    "",
                    "end",
                    values=(
                        record.day.isoformat(),
                        fmt_date_week(record.day).split()[-1],
                        fmt_km(record.distance_km, 2),
                        fmt_duration(record.duration_sec),
                        fmt_pace(record.pace_sec_per_km),
                        "有效" if record.valid else "无效",
                    ),
                    tags=tuple(tags),
                )
        note = summary.note or ""
        if summary.raw_record_count != summary.completed_runs:
            note = (note + "；" if note else "") + f"原始 {summary.raw_record_count} 条，按每天一次计 {summary.completed_runs} 条。"
        self.note.configure(text=note)

    def _clear_tree(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _show_empty(self, text: str) -> None:
        self.tree.pack_forget()
        self.empty_label.configure(text=text)
        self.empty_label.place(relx=0.5, rely=0.45, anchor="center")

    def _hide_empty(self) -> None:
        self.empty_label.place_forget()
        self.tree.pack(side="left", fill="both", expand=True)
