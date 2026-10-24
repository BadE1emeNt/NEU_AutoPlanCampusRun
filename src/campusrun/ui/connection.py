"""连接页：粘贴 cURL、预览响应、自动识别与保存（DPAPI 加密）。"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

from ..curlparse import parse_capture
from ..errors import CampusRunError
from ..jsonpath import preview_json
from ..models import FieldMapping, HttpConnection
from ..providers import HttpProvider
from ..providers.autodetect import describe_result, detect, summary_from_payload
from .theme import (
    ACCENT,
    BG,
    BORDER,
    CARD,
    CARD_ALT,
    DANGER,
    FAINT,
    MUTED,
    SUCCESS,
    TEXT,
    WARN,
    font,
)
from .widgets import Card, Pill, ScrollFrame, section_title


class ConnectionPage(tk.Frame):
    def __init__(self, master: tk.Misc, app):
        super().__init__(master, bg=BG)
        self.app = app
        self._request = None
        self._payload = None
        self._mapping: FieldMapping | None = None
        self._busy = False
        self._build()
        self._load_existing_mapping()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.scroll = ScrollFrame(self, bg=BG)
        self.scroll.pack(fill="both", expand=True)
        root = self.scroll.inner

        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=30, pady=(24, 12))
        left = tk.Frame(header, bg=BG)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="连接真实账号", bg=BG, fg=TEXT, font=font("h1"), anchor="w").pack(anchor="w")
        tk.Label(
            left,
            text="只读取统计与记录，不提交跑步、不修改账号；凭据用 Windows DPAPI 加密保存在本机。",
            bg=BG,
            fg=MUTED,
            font=font("small"),
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(anchor="w", pady=(5, 0))
        ttk.Button(header, text="抓包指引", command=lambda: self.app.show_page("help")).pack(side="right")

        self._build_status(root)
        self._build_capture(root)
        self._build_preview(root)
        self._build_mapping(root)
        self._build_footer(root)

    def _build_status(self, parent: tk.Misc) -> None:
        card = Card(parent, padding=18)
        card.pack(fill="x", padx=30, pady=8)
        head = tk.Frame(card.body, bg=CARD)
        head.pack(fill="x")
        section_title(head, "数据源状态", "").pack(side="left")
        self.mode_pill = Pill(head, "未连接", "muted")
        self.mode_pill.pack(side="right")

        self.conn_detail = tk.Label(
            card.body,
            text="",
            bg=CARD,
            fg=MUTED,
            font=font("small"),
            anchor="w",
            justify="left",
            wraplength=980,
        )
        self.conn_detail.pack(anchor="w", pady=(8, 0))

        metrics = tk.Frame(card.body, bg=CARD)
        metrics.pack(fill="x", pady=(12, 4))
        for column in range(3):
            metrics.grid_columnconfigure(column, weight=1, uniform="conn")
        self.metric_source = self._metric(metrics, 0, "数据来源")
        self.metric_security = self._metric(metrics, 1, "凭据保存")
        self.metric_time = self._metric(metrics, 2, "上次获取")

        actions = tk.Frame(card.body, bg=CARD)
        actions.pack(fill="x", pady=(10, 0))
        self.demo_var = tk.BooleanVar(value=True)
        self.demo_check = tk.Checkbutton(
            actions,
            text="使用演示数据（不联网）",
            variable=self.demo_var,
            command=self._toggle_demo,
            bg=CARD,
            fg=TEXT,
            activebackground=CARD,
            activeforeground=TEXT,
            selectcolor="#FFFFFF",
            highlightthickness=0,
            bd=0,
            font=font("small"),
            anchor="w",
        )
        self.demo_check.pack(side="left")
        ttk.Button(actions, text="打开数据目录", command=self._open_folder).pack(side="right")
        self.clear_conn_btn = ttk.Button(
            actions,
            text="清除连接",
            style="Danger.TButton",
            command=self._clear_connection,
        )
        self.clear_conn_btn.pack(side="right", padx=(0, 8))

    def _metric(self, parent: tk.Misc, column: int, title: str) -> tk.Label:
        box = tk.Frame(parent, bg=CARD)
        box.grid(row=0, column=column, sticky="w", padx=8)
        tk.Label(box, text=title, bg=CARD, fg=FAINT, font=font("tiny"), anchor="w").pack(anchor="w")
        value = tk.Label(box, text="—", bg=CARD, fg=TEXT, font=(font("small")[0], 9, "bold"), anchor="w")
        value.pack(anchor="w", pady=(2, 0))
        return value

    def _build_capture(self, parent: tk.Misc) -> None:
        card = Card(parent, padding=18)
        card.pack(fill="x", padx=30, pady=8)
        section_title(
            card.body,
            "① 粘贴抓包请求",
            "抓包工具里对“返回跑步记录/统计”的请求右键 → Copy as cURL；支持 Linux/macOS 和 Windows 两种格式。",
        ).pack(anchor="w")

        wrap = tk.Frame(card.body, bg=CARD)
        wrap.pack(fill="x", pady=(12, 0))
        self.curl_text = tk.Text(
            wrap,
            height=7,
            bg=CARD_ALT,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            font=font("mono"),
            wrap="word",
            padx=10,
            pady=8,
        )
        self.curl_text.pack(side="left", fill="both", expand=True)
        curl_scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.curl_text.yview)
        curl_scroll.pack(side="right", fill="y")
        self.curl_text.configure(yscrollcommand=curl_scroll.set)

        actions = tk.Frame(card.body, bg=CARD)
        actions.pack(fill="x", pady=(10, 0))
        self.parse_btn = ttk.Button(
            actions,
            text="解析并测试",
            style="Accent.TButton",
            command=self._parse_and_fetch,
        )
        self.parse_btn.pack(side="left")
        ttk.Button(actions, text="清空", command=self._clear_form).pack(side="left", padx=(8, 0))
        self.capture_status = tk.Label(
            actions,
            text="尚未粘贴",
            bg=CARD,
            fg=MUTED,
            font=font("small"),
            anchor="w",
            justify="left",
        )
        self.capture_status.pack(side="left", padx=(14, 0), fill="x", expand=True)

    def _build_preview(self, parent: tk.Misc) -> None:
        card = Card(parent, padding=18)
        card.pack(fill="x", padx=30, pady=8)
        section_title(
            card.body,
            "② 响应预览与自动识别",
            "只在本机显示；不会上传。若接口已过期，会返回 401/403 或登录页。",
        ).pack(anchor="w")

        self.detect_label = tk.Label(
            card.body,
            text="等待请求…",
            bg=CARD,
            fg=MUTED,
            font=font("small"),
            anchor="w",
            justify="left",
            wraplength=980,
        )
        self.detect_label.pack(anchor="w", pady=(10, 8))

        wrap = tk.Frame(card.body, bg=CARD)
        wrap.pack(fill="x")
        self.preview_text = tk.Text(
            wrap,
            height=10,
            bg=CARD_ALT,
            fg=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            font=font("mono_small"),
            wrap="none",
            state="disabled",
            padx=10,
            pady=8,
        )
        self.preview_text.pack(side="left", fill="both", expand=True)
        preview_scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.preview_text.yview)
        preview_scroll.pack(side="right", fill="y")
        self.preview_text.configure(yscrollcommand=preview_scroll.set)

    def _build_mapping(self, parent: tk.Misc) -> None:
        card = Card(parent, padding=18)
        card.pack(fill="x", padx=30, pady=8)
        section_title(
            card.body,
            "③ 字段映射（自动识别后可微调）",
            "JSON 路径用点号：data.list；字段名写记录内部键名，也支持嵌套路径。",
        ).pack(anchor="w")

        grid = tk.Frame(card.body, bg=CARD)
        grid.pack(fill="x", pady=(12, 0))
        for column in range(4):
            grid.grid_columnconfigure(column, weight=1 if column in (1, 3) else 0)

        self.mapping_vars: dict[str, tk.StringVar] = {
            key: tk.StringVar()
            for key in (
                "mode",
                "records_path",
                "date_field",
                "distance_field",
                "duration_field",
                "valid_field",
                "id_field",
                "distance_unit",
                "time_unit",
                "total_distance_path",
                "total_runs_path",
            )
        }
        self._reset_mapping_defaults()

        self._field_entry(grid, 0, 0, "模式", "mode", width=12, values=("records", "aggregate"))
        self._field_entry(grid, 0, 2, "距离单位", "distance_unit", width=12, values=("auto", "km", "m"))
        self._field_entry(grid, 1, 0, "记录数组路径", "records_path", span=3, width=52)
        self._field_entry(grid, 2, 0, "日期字段", "date_field")
        self._field_entry(grid, 2, 2, "里程字段", "distance_field")
        self._field_entry(grid, 3, 0, "用时字段", "duration_field")
        self._field_entry(grid, 3, 2, "有效标记字段", "valid_field")
        self._field_entry(grid, 4, 0, "记录 ID 字段", "id_field")
        self._field_entry(grid, 4, 2, "时间单位", "time_unit", width=12, values=("auto", "s", "ms", "min"))
        self._field_entry(grid, 5, 0, "总里程路径（汇总模式）", "total_distance_path")
        self._field_entry(grid, 5, 2, "总次数路径（汇总模式）", "total_runs_path")

        actions = tk.Frame(card.body, bg=CARD)
        actions.pack(fill="x", pady=(14, 0))
        self.reparse_btn = ttk.Button(actions, text="按当前映射重新解析", command=self._reparse)
        self.reparse_btn.pack(side="left")
        self.save_btn = ttk.Button(
            actions,
            text="保存连接",
            style="Accent.TButton",
            command=self._save,
            state="disabled",
        )
        self.save_btn.pack(side="left", padx=(8, 0))
        self.mapping_status = tk.Label(
            actions,
            text="",
            bg=CARD,
            fg=MUTED,
            font=font("small"),
            anchor="w",
            justify="left",
        )
        self.mapping_status.pack(side="left", padx=(14, 0), fill="x", expand=True)

    def _field_entry(
        self,
        parent: tk.Misc,
        row: int,
        column: int,
        label: str,
        key: str,
        width: int = 24,
        values: tuple[str, ...] | None = None,
        span: int = 1,
    ) -> None:
        box = tk.Frame(parent, bg=CARD)
        box.grid(row=row, column=column, columnspan=span, sticky="ew", padx=6, pady=5)
        tk.Label(box, text=label, bg=CARD, fg=MUTED, font=font("tiny"), anchor="w").pack(anchor="w")
        var = self.mapping_vars[key]
        if values:
            widget: tk.Widget = ttk.Combobox(
                box,
                textvariable=var,
                values=values,
                state="readonly",
                width=width,
            )
        else:
            widget = ttk.Entry(box, textvariable=var, width=width)
        widget.pack(anchor="w", fill="x", pady=(2, 0))

    def _build_footer(self, parent: tk.Misc) -> None:
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", padx=30, pady=(4, 26))
        tk.Label(
            frame,
            text=(
                "安全提示：cURL 里包含登录令牌，等同于密码。连接文件用当前 Windows 账户的 DPAPI 加密，"
                "换机器/换账户无法解密；不要把抓包内容发到公开群聊或截图里。"
            ),
            bg=BG,
            fg=FAINT,
            font=font("tiny"),
            anchor="w",
            justify="left",
            wraplength=1000,
        ).pack(anchor="w")

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        service = self.app.service
        if service.is_demo:
            self.mode_pill.set("演示模式", "accent")
        elif service.has_connection:
            self.mode_pill.set("已连接", "success")
        else:
            self.mode_pill.set("未连接", "muted")

        self.demo_var.set(service.config.demo_mode)
        self.metric_source.configure(text=service.source_text())
        if service.connection is None:
            self.metric_security.configure(text="未配置")
            self.metric_time.configure(text="—")
            self.conn_detail.configure(text="当前没有保存任何真实接口。按下面的步骤抓包后粘贴 cURL。")
        else:
            mapping = service.connection.mapping
            self.metric_security.configure(
                text="DPAPI 加密" if service.connection_encrypted else "明文（DPAPI 不可用）"
            )
            if service.summary:
                self.metric_time.configure(text=service.summary.fetched_at.strftime("%Y-%m-%d %H:%M"))
            else:
                self.metric_time.configure(text="—")
            self.conn_detail.configure(
                text=(
                    f"接口：{service.connection.request.method} {service.connection.request.host}  ·  "
                    f"{mapping.describe()}"
                )
            )
            if self._mapping is None:
                self._sync_mapping_fields(mapping)
        self.clear_conn_btn.configure(state="normal" if service.has_connection else "disabled")
        self.save_btn.configure(state="normal" if (self._request and self._payload) else "disabled")

    def _load_existing_mapping(self) -> None:
        if self.app.service.connection is not None:
            self._sync_mapping_fields(self.app.service.connection.mapping)

    def _sync_mapping_fields(self, mapping: FieldMapping) -> None:
        values = mapping.to_dict()
        for key, var in self.mapping_vars.items():
            var.set(str(values.get(key, "") or ""))

    def _reset_mapping_defaults(self) -> None:
        for key, var in self.mapping_vars.items():
            var.set("")
        self.mapping_vars["mode"].set("records")
        self.mapping_vars["distance_unit"].set("auto")
        self.mapping_vars["time_unit"].set("auto")
        self.mapping_vars["date_field"].set("date")
        self.mapping_vars["distance_field"].set("distance")

    def _mapping_from_fields(self) -> FieldMapping:
        values = {key: var.get().strip() for key, var in self.mapping_vars.items()}
        return FieldMapping.from_dict(values)

    # ------------------------------------------------------------------
    def _parse_and_fetch(self) -> None:
        text = self.curl_text.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("还没有内容", "请先粘贴抓包得到的 cURL。", parent=self.app)
            return
        try:
            request = parse_capture(text)
        except CampusRunError as exc:
            messagebox.showerror("无法解析", str(exc), parent=self.app)
            return
        self._request = request
        self._payload = None
        self._mapping = None
        self.save_btn.configure(state="disabled")
        self.capture_status.configure(
            text=f"已识别：{request.method} {request.host}{request.path}", fg=SUCCESS
        )
        self.detect_label.configure(text="正在请求接口…", fg=MUTED)
        self._set_busy(True)

        connection = HttpConnection(request=request, mapping=FieldMapping())
        self.app.run_async(
            lambda: HttpProvider(connection).fetch_json(),
            self._on_fetched,
            self._on_fetch_failed,
        )

    def _on_fetched(self, payload) -> None:
        self._set_busy(False)
        self._payload = payload
        self._set_preview(preview_json(payload))
        try:
            detection = detect(payload)
        except CampusRunError as exc:
            self.detect_label.configure(text=f"未能自动识别：{exc}", fg=WARN)
            self.save_btn.configure(state="normal")
            return
        self._mapping = detection.mapping
        self._sync_mapping_fields(detection.mapping)
        try:
            summary = summary_from_payload(
                payload,
                detection.mapping,
                provider=self._request.host if self._request else "抓包接口",
                count_mode=self.app.service.config.count_mode,
            )
        except CampusRunError as exc:
            self.detect_label.configure(text=f"{detection.notes}\n映射未通过：{exc}", fg=WARN)
        else:
            self.detect_label.configure(
                text=(
                    f"{detection.notes}  "
                    f"{describe_result(payload, detection.mapping)}"
                ),
                fg=SUCCESS,
            )
            self.mapping_status.configure(text=f"可保存：{summary.completed_runs} 次 / {summary.completed_km:.1f} km", fg=SUCCESS)
        self.save_btn.configure(state="normal")
        self.capture_status.configure(text="请求成功", fg=SUCCESS)

    def _on_fetch_failed(self, exc: Exception) -> None:
        self._set_busy(False)
        self.capture_status.configure(text="请求失败", fg=DANGER)
        self.detect_label.configure(text=f"请求失败：{exc}", fg=DANGER)
        self._set_preview(f"请求失败：\n{exc}")
        messagebox.showerror("请求失败", str(exc), parent=self.app)

    def _reparse(self) -> None:
        if self._payload is None:
            messagebox.showinfo("还没有响应", "请先粘贴 cURL 并点“解析并测试”。", parent=self.app)
            return
        mapping = self._mapping_from_fields()
        self._mapping = mapping
        try:
            summary = summary_from_payload(
                self._payload,
                mapping,
                provider=self._request.host if self._request else "抓包接口",
                count_mode=self.app.service.config.count_mode,
            )
        except CampusRunError as exc:
            self.mapping_status.configure(text=str(exc), fg=DANGER)
            return
        self.mapping_status.configure(
            text=f"解析成功：{summary.completed_runs} 次 / {summary.completed_km:.1f} km",
            fg=SUCCESS,
        )
        self.detect_label.configure(text=describe_result(self._payload, mapping), fg=SUCCESS)

    def _save(self) -> None:
        if self._request is None or self._payload is None:
            messagebox.showinfo("还没有可用连接", "请先粘贴 cURL 并成功请求一次。", parent=self.app)
            return
        mapping = self._mapping_from_fields()
        try:
            summary = summary_from_payload(
                self._payload,
                mapping,
                provider=self._request.host,
                count_mode=self.app.service.config.count_mode,
            )
        except CampusRunError as exc:
            messagebox.showerror("字段映射不完整", str(exc), parent=self.app)
            return
        try:
            secure = self.app.service.save_connection(self._request, mapping)
            self.app.service.adopt_summary(summary)
        except CampusRunError as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.app)
            return
        self._mapping = mapping
        self.demo_var.set(False)
        self.app.refresh_views()
        self.app.set_status("真实数据已连接", "success")
        text = "连接已保存。" + ("凭据已用 DPAPI 加密。" if secure else "警告：DPAPI 不可用，凭据以明文保存。")
        messagebox.showinfo("保存成功", text, parent=self.app)
        self.app.show_page("dashboard")

    def _toggle_demo(self) -> None:
        enabled = bool(self.demo_var.get())
        if not enabled and not self.app.service.has_connection:
            self.demo_var.set(True)
            messagebox.showinfo("还没有连接", "请先抓包并保存真实接口，再关闭演示数据。", parent=self.app)
            return
        self.app.set_demo_mode(enabled)
        if not enabled:
            self.app.refresh_data()

    def _clear_connection(self) -> None:
        if not self.app.service.has_connection:
            return
        if not messagebox.askyesno(
            "清除连接",
            "会删除加密保存的 cURL 凭据与缓存数据（不会影响小程序里的真实记录）。继续？",
            parent=self.app,
        ):
            return
        self.app.service.clear_connection()
        self._request = None
        self._payload = None
        self._mapping = None
        self._clear_form()
        self.demo_var.set(True)
        self.app.refresh_views()
        self.app.set_status("已切换回演示数据", "accent")

    def _clear_form(self) -> None:
        self.curl_text.delete("1.0", "end")
        self._set_preview("")
        self.detect_label.configure(text="等待请求…", fg=MUTED)
        self.capture_status.configure(text="尚未粘贴", fg=MUTED)
        self.mapping_status.configure(text="")
        self._reset_mapping_defaults()
        self.save_btn.configure(state="disabled")

    def _set_preview(self, text: str) -> None:
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.parse_btn.configure(
            state="disabled" if busy else "normal",
            text="请求中…" if busy else "解析并测试",
        )
        self.app.set_busy(busy)

    def _open_folder(self) -> None:
        try:
            os.startfile(str(self.app.service.paths.home))  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("无法打开目录", str(exc), parent=self.app)
