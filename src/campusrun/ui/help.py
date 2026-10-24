"""抓包帮助页：三条路线、通用步骤、排查与安全说明。"""

from __future__ import annotations

import os
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from .theme import (
    ACCENT,
    BG,
    CARD,
    CARD_ALT,
    FAINT,
    MUTED,
    TEXT,
    WARN,
    font,
)
from .widgets import Card, LinkLabel, ScrollFrame, section_title


class HelpPage(tk.Frame):
    def __init__(self, master: tk.Misc, app):
        super().__init__(master, bg=BG)
        self.app = app
        self._build()

    def _build(self) -> None:
        self.scroll = ScrollFrame(self, bg=BG)
        self.scroll.pack(fill="both", expand=True)
        root = self.scroll.inner

        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=30, pady=(24, 12))
        header.grid_columnconfigure(0, weight=1)
        left = tk.Frame(header, bg=BG)
        left.grid(row=0, column=0, sticky="w")
        tk.Label(left, text="抓包登录（备用）", bg=BG, fg=TEXT, font=font("h1"), anchor="w").pack(anchor="w")
        tk.Label(
            left,
            text="只有账号登录失败或无法通过验证时再用；抓包请求等同于登录令牌。",
            bg=BG,
            fg=MUTED,
            font=font("small"),
            anchor="w",
            justify="left",
            wraplength=760,
        ).pack(anchor="w", pady=(5, 0))
        actions = tk.Frame(header, bg=BG)
        actions.grid(row=0, column=1, sticky="e")
        ttk.Button(actions, text="使用指南", command=lambda: self.app.show_onboarding(force=True)).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(actions, text="打开完整指南", command=self._open_docs).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="打开数据目录", command=self._open_data_dir).pack(side="left")

        routes = tk.Frame(root, bg=BG)
        routes.pack(fill="x", padx=24, pady=6)
        for column in range(3):
            routes.grid_columnconfigure(column, weight=1, uniform="route")
        self._route_card(
            routes,
            0,
            "Windows 微信（推荐）",
            "电脑和手机同一网络；微信 PC 版能打开该小程序时最省事。",
            [
                "安装 mitmproxy 或 Fiddler Classic，开启系统代理 127.0.0.1:8080。",
                "信任抓包工具的根证书（系统证书管理器）。",
                "微信 PC 打开小程序，进入跑步记录/统计页并下拉刷新。",
                "在抓包工具里找到 JSON 响应，右键 Copy as cURL。",
            ],
        )
        self._route_card(
            routes,
            1,
            "Android 手机",
            "适合小程序只能在手机端打开的情况。",
            [
                "安装 Reqable / HttpCanary 等支持 VPN 抓包的工具，启动抓包。",
                "安装它的 CA 证书；Android 7+ 默认不信任用户证书，可能需要 root 或模拟器。",
                "打开小程序 → 跑步记录页 → 下拉刷新。",
                "长按请求导出 cURL / HAR，发到电脑。",
            ],
        )
        self._route_card(
            routes,
            2,
            "iPhone / iPad",
            "Charles + iOS 对用户证书的支持较好。",
            [
                "电脑装 Charles，手机 Wi-Fi 设 HTTP 代理到电脑。",
                "Safari 打开 chls.pro/ssl 安装描述文件。",
                "设置 → 通用 → 关于本机 → 证书信任设置，打开 Charles 信任。",
                "在小程序里刷新记录页，找到请求后导出 cURL。",
            ],
        )

        self._steps_card(root)
        self._troubleshoot_card(root)
        self._security_card(root)
        self._developer_card(root)

    def _route_card(self, parent: tk.Misc, column: int, title: str, subtitle: str, steps: list[str]) -> None:
        card = Card(parent, padding=16)
        card.grid(row=0, column=column, sticky="nsew", padx=6, pady=6)
        tk.Label(card.body, text=title, bg=CARD, fg=TEXT, font=font("h3"), anchor="w").pack(anchor="w")
        tk.Label(
            card.body,
            text=subtitle,
            bg=CARD,
            fg=FAINT,
            font=font("tiny"),
            anchor="w",
            justify="left",
            wraplength=250,
        ).pack(anchor="w", pady=(3, 8))
        for index, step in enumerate(steps, 1):
            row = tk.Frame(card.body, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(
                row,
                text=f"{index}",
                bg=CARD_ALT,
                fg=MUTED,
                font=font("tiny"),
                width=2,
            ).pack(side="left", anchor="n", pady=(1, 0))
            tk.Label(
                row,
                text=step,
                bg=CARD,
                fg=MUTED,
                font=font("tiny"),
                anchor="w",
                justify="left",
                wraplength=225,
            ).pack(side="left", fill="x", expand=True, padx=(6, 0))

    def _steps_card(self, parent: tk.Misc) -> None:
        card = Card(parent, padding=20)
        card.pack(fill="x", padx=30, pady=8)
        section_title(
            card.body,
            "找到“正确的那条请求”",
            "小程序一次刷新会发很多请求；要找返回里含 distance / totalDistance / records 的那条。",
        ).pack(anchor="w")

        steps = [
            "先进入小程序的“跑步记录 / 我的里程 / 统计”页面，下拉刷新，让请求出现在抓包列表里。",
            "按域名过滤，逐个看响应：JSON 里出现 distance、totalDistance、mileage、records、runList 等字段。",
            "确认响应里能看到你的累计次数/公里数，或者逐条跑步记录。",
            "右键该请求 → Copy as cURL；手机端则导出 cURL/HAR 后发到电脑。",
            "回到本程序“连接”页粘贴，点“解析并测试”，确认识别出的次数与里程和页面一致。",
        ]
        for index, step in enumerate(steps, 1):
            row = tk.Frame(card.body, bg=CARD)
            row.pack(fill="x", pady=3)
            tk.Label(
                row,
                text=f"{index:02d}",
                bg=CARD,
                fg=ACCENT,
                font=(font("small")[0], 9, "bold"),
                width=3,
                anchor="w",
            ).pack(side="left", anchor="n")
            tk.Label(
                row,
                text=step,
                bg=CARD,
                fg=MUTED,
                font=font("small"),
                anchor="w",
                justify="left",
                wraplength=800,
            ).pack(side="left", fill="x", expand=True)

        note = tk.Frame(card.body, bg=CARD_ALT)
        note.pack(fill="x", pady=(12, 0))
        tk.Label(
            note,
            text=(
                "提示：只读请求就够了。请勿抓取或提交跑步数据、不要伪造轨迹；本程序也不会自动提交任何记录。"
            ),
            bg=CARD_ALT,
            fg=MUTED,
            font=font("small"),
            anchor="w",
            justify="left",
            wraplength=820,
            padx=12,
            pady=9,
        ).pack(fill="x")

    def _troubleshoot_card(self, parent: tk.Misc) -> None:
        card = Card(parent, padding=20)
        card.pack(fill="x", padx=30, pady=8)
        section_title(card.body, "常见问题", "").pack(anchor="w")

        items = (
            (
                "401 / 403 / “登录失效”",
                "令牌过期。重新进入小程序刷新记录页，重新抓一条 cURL 覆盖即可。",
            ),
            (
                "返回 HTML、登录页或网关页",
                "请求被重定向到登录/网关，说明凭据已失效；也可能电脑网络无法直连校园接口，试试校园网。",
            ),
            (
                "抓不到 HTTPS / 0 字节",
                "根证书没信任，或 App 不走系统代理。Windows 微信路线最容易成功；Android 7+ 需要系统证书。",
            ),
            (
                "小程序打不开或一直转圈",
                "部分小程序会检测代理。先关闭代理进入页面，再开代理刷新；或改用手机流量抓包。",
            ),
            (
                "识别不出记录",
                "接口可能只返回汇总字段，程序会自动切到“汇总模式”；仍不行就在高级映射里手工填 JSON 路径。",
            ),
            (
                "换了电脑/Windows 账户后连不上",
                "DPAPI 只能在同一账户解密。重新抓包保存即可。",
            ),
        )
        for title, detail in items:
            row = tk.Frame(card.body, bg=CARD)
            row.pack(fill="x", pady=4)
            tk.Label(
                row,
                text="•",
                bg=CARD,
                fg=WARN,
                font=font("small"),
            ).pack(side="left", anchor="n")
            text = tk.Frame(row, bg=CARD)
            text.pack(side="left", fill="x", expand=True, padx=(8, 0))
            tk.Label(text, text=title, bg=CARD, fg=TEXT, font=font("h3"), anchor="w").pack(anchor="w")
            tk.Label(
                text,
                text=detail,
                bg=CARD,
                fg=MUTED,
                font=font("small"),
                anchor="w",
                justify="left",
                wraplength=820,
            ).pack(anchor="w")

    def _security_card(self, parent: tk.Misc) -> None:
        card = Card(parent, padding=20)
        card.pack(fill="x", padx=30, pady=8)
        section_title(card.body, "安全与合规", "").pack(anchor="w")
        lines = [
            "凭据只保存在本机 %APPDATA%\\CampusRun\\connection.dat，使用 Windows DPAPI 绑定当前账户。",
            "程序只发送你抓下来的那条查询请求，不修改账号、不提交跑步、不自动刷里程。",
            "cURL 里的 Authorization / Cookie 等同密码：不要发到公开群、不要把预览截图外传。",
            "需要作废时，在小程序里退出登录或重新登录即可让旧令牌失效。",
        ]
        for line in lines:
            tk.Label(
                card.body,
                text=f"· {line}",
                bg=CARD,
                fg=MUTED,
                font=font("small"),
                anchor="w",
                justify="left",
                wraplength=820,
            ).pack(anchor="w", pady=2)

    def _developer_card(self, parent: tk.Misc) -> None:
        card = Card(parent, padding=20)
        card.pack(fill="x", padx=30, pady=(8, 26))
        section_title(
            card.body,
            "识别失败时，需要你提供这些信息",
            "把值打码，只保留结构/字段名即可；不要发真实 token。",
        ).pack(anchor="w")
        lines = [
            "客户端：微信 PC / Android / iOS，以及小程序名称、版本（如果有）。",
            "请求：方法 + 域名 + 路径（query 里的 token 打码）。",
            "响应 JSON：字段结构，例如 data.list[].{runDate,distance,duration}，数值可改成 0。",
            "本程序显示的报错文本，或“解析并测试”的识别结果。",
            "你的目标里程与截止日期（用于核对规划结果是否符合学校规则）。",
        ]
        for line in lines:
            tk.Label(
                card.body,
                text=f"· {line}",
                bg=CARD,
                fg=MUTED,
                font=font("small"),
                anchor="w",
                justify="left",
                wraplength=820,
            ).pack(anchor="w", pady=2)

        links = tk.Frame(card.body, bg=CARD)
        links.pack(fill="x", pady=(12, 0))
        for text, url in (
            ("mitmproxy 文档", "https://docs.mitmproxy.org/stable/"),
            ("Reqable", "https://reqable.com/"),
            ("Fiddler", "https://www.telerik.com/fiddler"),
        ):
            link = LinkLabel(links, text, lambda u=url: webbrowser.open(u), bg=CARD)
            link.pack(side="left", padx=(0, 16))

    def _open_docs(self) -> None:
        path = Path(__file__).resolve().parents[3] / "docs" / "CAPTURE.md"
        if not path.exists():
            messagebox.showinfo("找不到文档", f"未找到 {path}", parent=self.app)
            return
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("无法打开", str(exc), parent=self.app)

    def _open_data_dir(self) -> None:
        try:
            os.startfile(str(self.app.service.paths.home))  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("无法打开", str(exc), parent=self.app)

    def refresh(self) -> None:  # 帮助页无动态数据
        return
