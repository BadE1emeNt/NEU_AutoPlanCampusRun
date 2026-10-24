"""命令行入口：``python -m campusrun ...``。

GUI 是主界面；CLI 用于快速查看规划、导入抓包、排查环境。
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from . import __app_name__, __version__
from .analysis import PlanResult, PlanSettings, Progress, build_plan
from .config import AppPaths, config_summary
from .curlparse import describe_capture, parse_capture
from .errors import CampusRunError
from .formatting import (
    fmt_date_short,
    fmt_date_week,
    fmt_duration,
    fmt_km,
    fmt_km_compact,
    fmt_minutes,
    fmt_pace,
    fmt_signed_days,
)
from .models import FieldMapping, HttpConnection
from .neu.cas import CasGuideRequired
from .providers import HttpProvider, MockProvider
from .providers.autodetect import describe_result, detect, summary_from_payload
from .service import CampusRunService

WEEKDAYS = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
}


def _parse_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"日期格式应为 YYYY-MM-DD：{text}") from exc


def _parse_rest(text: str) -> frozenset[int]:
    if not text or text.lower() in ("none", "无"):
        return frozenset()
    days: set[int] = set()
    for token in text.replace("，", ",").split(","):
        key = token.strip().lower().replace("周", "")
        if not key:
            continue
        if key.isdigit() and 0 <= int(key) <= 6:
            days.add(int(key))
        elif key in WEEKDAYS:
            days.add(WEEKDAYS[key])
        else:
            raise argparse.ArgumentTypeError(f"无法识别的休息日：{token}（用 mon,tue 或 0,1）")
    return frozenset(days)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="campusrun",
        description="东北大学校园乐跑：读取进度、规划每天跑量与完成天数。",
    )
    parser.add_argument("--home", type=Path, help="数据目录（默认 %%APPDATA%%\\CampusRun）")
    parser.add_argument("--debug", action="store_true", help="显示完整异常堆栈")
    parser.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gui", help="打开 Windows 桌面面板（默认）")

    plan = sub.add_parser("plan", help="计算每天需要跑多少 / 几天完成")
    plan.add_argument("--target", type=float, help="目标里程 km")
    plan.add_argument("--deadline", type=_parse_date, help="截止日期 YYYY-MM-DD")
    plan.add_argument("--done-km", type=float, help="手动指定已完成 km（覆盖已抓取数据）")
    plan.add_argument("--done-runs", type=int, default=0, help="手动指定已完成次数")
    plan.add_argument("--rest", type=_parse_rest, help="每周休息日，如 sat,sun 或 5,6")
    plan.add_argument("--pace", type=float, help="配速 min/km（默认 6.5）")
    plan.add_argument("--demo", action="store_true", help="使用演示进度，忽略真实缓存")
    plan.add_argument("--json", action="store_true", help="输出 JSON")

    fetch = sub.add_parser("fetch", help="按已保存的登录态拉取一次数据")
    fetch.add_argument("--json", action="store_true", help="输出 JSON")
    fetch.add_argument("--limit", type=int, default=10, help="最多显示多少条记录")

    login = sub.add_parser("login", help="用学号/密码登录学校统一身份认证")
    login.add_argument("--user", help="学号（不填则交互输入）")
    login.add_argument("--remember", action="store_true", help="用 DPAPI 保存密码，便于会话过期后自动重登")

    sub.add_parser("logout", help="清除本机保存的体育平台会话与密码")

    imp = sub.add_parser("import-curl", help="解析 cURL、预览响应、保存连接")
    imp.add_argument("--file", type=Path, help="包含 cURL 的文本文件（默认从标准输入读取）")
    imp.add_argument("--label", default="", help="连接名称，默认取域名")
    imp.add_argument("--no-save", action="store_true", help="只预览，不保存")

    config = sub.add_parser("config", help="查看或重置配置")
    config.add_argument("action", choices=["show", "reset"], nargs="?", default="show")
    config.add_argument("--yes", action="store_true", help="reset 时确认")

    sub.add_parser("doctor", help="检查 Python / tkinter / DPAPI / 配置目录")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args.command = "gui"

    paths = AppPaths(args.home.resolve()) if args.home else AppPaths.default()
    try:
        paths.ensure()
        if args.command == "gui":
            return _run_gui(paths)
        service = CampusRunService(paths)
        if args.command == "plan":
            return _cmd_plan(service, args)
        if args.command == "fetch":
            return _cmd_fetch(service, args)
        if args.command == "login":
            return _cmd_login(service, args)
        if args.command == "logout":
            return _cmd_logout(service)
        if args.command == "import-curl":
            return _cmd_import(service, args)
        if args.command == "config":
            return _cmd_config(service, args)
        if args.command == "doctor":
            return _cmd_doctor(service)
        parser.print_help()
        return 2
    except CampusRunError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        if args.debug:
            raise
        return 1
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI 顶层兜底
        if args.debug:
            raise
        print(f"未预期的错误：{type(exc).__name__}: {exc}", file=sys.stderr)
        print("加 --debug 查看完整堆栈。", file=sys.stderr)
        return 1


def _run_gui(paths: AppPaths) -> int:
    try:
        from .ui.app import run_app
    except ImportError as exc:
        print(f"无法加载图形界面：{exc}", file=sys.stderr)
        print("请确认 Python 安装包含 tkinter。", file=sys.stderr)
        return 1
    return run_app(paths)


def _settings_from_args(service: CampusRunService, args: argparse.Namespace) -> PlanSettings:
    base = service.config
    return PlanSettings(
        target_km=args.target if args.target is not None else base.target_km,
        deadline=args.deadline if args.deadline is not None else base.deadline,
        min_run_km=base.min_run_km,
        max_run_km=base.max_run_km,
        rest_weekdays=args.rest if args.rest is not None else frozenset(base.rest_weekdays),
        pace_min_per_km=args.pace if args.pace is not None else base.pace_min_per_km,
    )


def _progress_from_args(service: CampusRunService, args: argparse.Namespace) -> Progress:
    if args.done_km is not None:
        return Progress(
            completed_km=args.done_km,
            completed_runs=args.done_runs,
            ran_today=False,
            source="命令行指定",
            has_data=True,
        )
    if args.demo or (service.summary is None and service.config.demo_mode):
        summary = MockProvider().fetch()
        return Progress.from_summary(summary)
    if service.summary is None:
        raise CampusRunError("还没有数据。请先运行 `campusrun login` 或 `campusrun fetch`。")
    return Progress.from_summary(service.summary)


def _cmd_plan(service: CampusRunService, args: argparse.Namespace) -> int:
    settings = _settings_from_args(service, args)
    progress = _progress_from_args(service, args)
    plan = build_plan(progress, settings)

    if args.json:
        print(json.dumps(_plan_to_dict(plan), ensure_ascii=False, indent=2))
        return 0
    _print_plan(plan, settings)
    return 0


def _print_plan(plan: PlanResult, settings: PlanSettings) -> None:
    source = plan.source if plan.has_data else "未连接（按 0 km 估算）"
    if not plan.has_data:
        source = "演示/缓存" if plan.source == "演示数据" else "未连接（按 0 km 估算）"
    print(f"{__app_name__} · 校园乐跑规划")
    print(f"数据：{source} · 已完成 {fmt_km(plan.completed_km)} / {plan.completed_runs} 次")
    print(
        f"目标：{fmt_km(plan.target_km)} · 截止 {plan.deadline.isoformat()}"
    )
    if plan.remaining_km <= 0:
        print("状态：目标已达成。")
        return
    need = f"{plan.required_per_day_km:.2f} km/天" if plan.available_days else "—"
    print(f"剩余：{fmt_km(plan.remaining_km)} → 摊到每个可跑日 {need}")
    if plan.first_run_day:
        print(f"可跑：{plan.available_days} 天（首日 {plan.first_run_day.isoformat()}）")
    print(
        f"最快：{plan.min_days} 个跑步日"
        + (f"，预计 {plan.earliest_finish.isoformat()} 完成（{fmt_signed_days(plan.slack_days)}）"
           if plan.earliest_finish else "，无法在截止日前完成")
    )
    print()
    print("每天跑        需要天数    完成日期      余量")
    print("-" * 52)
    for scenario in plan.scenarios:
        finish = fmt_date_short(scenario.finish) if scenario.finish else "—"
        slack = fmt_signed_days(scenario.slack_days) if scenario.slack_days is not None else "无法完成"
        print(f"{fmt_km_compact(scenario.per_day_km):<12}{scenario.days:>4} 天     {finish:<10}{slack}")
    if plan.schedule:
        print()
        print(f"最快安排（每次约 {plan.schedule[0].km:.1f} km）：")
        for run in plan.schedule:
            print(
                f"  {fmt_date_week(run.day)}  {run.km:.2f} km  "
                f"约 {fmt_minutes(run.minutes)}"
            )
    if plan.warnings:
        print()
        for warning in plan.warnings:
            print(f"提示：{warning}")
    print()
    print(
        f"规则：单次有效 {settings.min_run_km:g}–{settings.max_run_km:g} km，"
        f"每天最多 1 次，配速 {settings.pace_min_per_km:g} min/km 估算。"
    )


def _cli_sms(challenge) -> str:
    print(f"\n{getattr(challenge, 'hint', '需要短信验证码')}", file=sys.stderr)
    try:
        return input("短信验证码：").strip()
    except EOFError:
        return ""


def _cmd_login(service: CampusRunService, args: argparse.Namespace) -> int:
    username = (args.user or input("学号：")).strip()
    if not username:
        print("学号不能为空。", file=sys.stderr)
        return 2
    password = getpass.getpass("统一身份认证密码（不会显示）：")
    if not password and not service.has_saved_credentials:
        print("密码不能为空。", file=sys.stderr)
        return 2
    try:
        summary = service.login_neu(
            username,
            password,
            remember_password=bool(args.remember),
            sms_provider=_cli_sms,
        )
    except CasGuideRequired as exc:
        print(
            "\n需要先在浏览器完成一次首次登录引导。\n"
            "如果页面是“首次绑定邮箱”，直接点“稍后绑定”跳过即可。\n",
            file=sys.stderr,
        )
        print(exc.url, file=sys.stderr)
        print("\n完成后重新运行本命令。", file=sys.stderr)
        try:
            if sys.stdin.isatty():
                import webbrowser

                webbrowser.open(exc.url)
                print("已尝试用默认浏览器打开引导页。", file=sys.stderr)
        except Exception:
            pass
        return 2
    print(
        f"登录成功：{summary.completed_runs} 次有效记录，共 {summary.completed_km:.2f} km。"
    )
    if args.remember:
        print("密码已用 Windows DPAPI 保存；会话过期时可自动重登。")
    else:
        print("未保存密码；token 过期后需要重新运行 login。")
    return 0


def _cmd_logout(service: CampusRunService) -> int:
    service.clear_neu_login(clear_credentials=True)
    service.set_demo_mode(True)
    print("已清除本机的体育平台会话与保存的密码。")
    return 0


def _cmd_fetch(service: CampusRunService, args: argparse.Namespace) -> int:
    summary = service.refresh(_cli_sms)
    if args.json:
        print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
        return 0
    print(f"数据源：{summary.provider}（{summary.fetched_at.strftime('%Y-%m-%d %H:%M')}）")
    print(f"有效：{summary.completed_runs} 次 / {fmt_km(summary.completed_km)}")
    if summary.raw_record_count != summary.completed_runs:
        print(f"原始记录 {summary.raw_record_count} 条（同一天只取最远一次，按学校规则）")
    print()
    print("日期        星期  里程      用时      配速")
    print("-" * 48)
    for record in sorted(summary.records, key=lambda r: r.day, reverse=True)[: max(1, args.limit)]:
        print(
            f"{record.day.isoformat()}  {fmt_date_week(record.day).split()[-1]}  "
            f"{record.distance_km:>5.2f} km  {fmt_duration(record.duration_sec):>7}  "
            f"{fmt_pace(record.pace_sec_per_km)}"
        )
    if not summary.records:
        print("（接口只返回了汇总数据，没有逐条记录）")
    return 0


def _cmd_import(service: CampusRunService, args: argparse.Namespace) -> int:
    if args.file:
        text = args.file.read_text(encoding="utf-8-sig")
        origin = str(args.file)
    else:
        if sys.stdin.isatty():
            print("请粘贴 cURL，结束后按 Ctrl+Z 回车（Windows）：", file=sys.stderr)
        text = sys.stdin.read()
        origin = "标准输入"
    request = parse_capture(text)
    print(f"已解析 {origin}")
    print(describe_capture(request))
    print("正在请求接口…")
    provider = HttpProvider(HttpConnection(request=request, mapping=FieldMapping()))
    payload = provider.fetch_json()
    detection = detect(payload)
    print(f"自动识别：{detection.notes}")
    print(describe_result(payload, detection.mapping))
    if args.no_save:
        print("未保存（--no-save）。")
        return 0
    summary = summary_from_payload(
        payload,
        detection.mapping,
        provider=request.host,
        count_mode=service.config.count_mode,
    )
    secure = service.save_connection(request, detection.mapping, label=args.label)
    service.adopt_summary(summary)
    print(f"已保存连接：{'DPAPI 加密' if secure else '明文（DPAPI 不可用）'}")
    print(f"已缓存数据：{summary.completed_runs} 次 / {summary.completed_km:.1f} km")
    print("打开 `campusrun gui` 或运行 `campusrun fetch` 查看数据。")
    return 0


def _cmd_config(service: CampusRunService, args: argparse.Namespace) -> int:
    if args.action == "reset":
        if not args.yes:
            print("这会删除配置、连接与缓存。确认请加 --yes。", file=sys.stderr)
            return 2
        for path in (
            service.paths.config_file,
            service.paths.connection_file,
            service.paths.sports_session_file,
            service.paths.credentials_file,
            service.paths.cache_file,
        ):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        print("已重置配置、连接与缓存。")
        return 0
    print(f"配置目录：{service.paths.home}")
    print(f"配置文件：{service.paths.config_file}")
    print(
        f"连接文件：{service.paths.connection_file} "
        f"（{'已加密保存' if service.connection_encrypted else ('存在但未加密' if service.has_connection else '未配置')}）"
    )
    print(
        f"体育平台登录：{'已登录' if service.has_neu_session else '未登录'}"
        f"（{'DPAPI 加密' if service.neu_session_encrypted else '无会话'}）；"
        f"保存密码：{'是' if service.has_saved_credentials else '否'}"
    )
    print(f"缓存文件：{service.paths.cache_file}")
    print(f"当前配置：{config_summary(service.config)}")
    print(f"数据来源：{service.source_text()}")
    if service.startup_warnings:
        print("启动警告：")
        for warning in service.startup_warnings:
            print(f"  - {warning}")
    return 0


def _cmd_doctor(service: CampusRunService) -> int:
    print(f"{__app_name__} {__version__} 环境检查")
    print(f"Python：{sys.version.split()[0]}（{sys.executable}）")
    ok = True

    try:
        import tkinter

        print(f"tkinter：可用，Tk {tkinter.TkVersion}")
    except Exception as exc:  # noqa: BLE001
        print(f"tkinter：不可用（{exc}）")
        ok = False

    from .secrets import available as dpapi_available

    dpapi = dpapi_available()
    print(f"Windows DPAPI：{'可用（凭据加密保存）' if dpapi else '不可用（将降级为明文，注意风险）'}")

    try:
        probe = service.paths.home / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        print(f"数据目录：可写（{service.paths.home}）")
    except OSError as exc:
        print(f"数据目录：不可写（{exc}）")
        ok = False

    print(f"配置：{config_summary(service.config)}")
    print(f"连接：{'已配置' if service.has_connection else '未配置'}")
    print(
        f"账号登录：{'已登录（uid=' + (service.sports_session.uid if service.sports_session else '') + '）' if service.has_neu_session else '未登录'}"
        f"；保存密码：{'是' if service.has_saved_credentials else '否'}"
    )
    if service.summary is not None:
        print(
            f"缓存：{service.summary.provider} · {service.summary.completed_km:.1f} km / "
            f"{service.summary.completed_runs} 次 · {service.summary.fetched_at.strftime('%Y-%m-%d %H:%M')}"
        )
    else:
        print("缓存：无")
    for warning in service.startup_warnings:
        print(f"警告：{warning}")
    return 0 if ok else 1


def _plan_to_dict(plan: PlanResult) -> dict[str, Any]:
    def iso(value: date | None) -> str | None:
        return value.isoformat() if value else None

    return {
        "today": plan.today.isoformat(),
        "deadline": plan.deadline.isoformat(),
        "target_km": plan.target_km,
        "completed_km": plan.completed_km,
        "remaining_km": plan.remaining_km,
        "completed_runs": plan.completed_runs,
        "available_days": plan.available_days,
        "calendar_days_left": plan.calendar_days_left,
        "required_per_day_km": plan.required_per_day_km,
        "min_days": plan.min_days,
        "earliest_finish": iso(plan.earliest_finish),
        "first_run_day": iso(plan.first_run_day),
        "slack_days": plan.slack_days,
        "max_reachable_km": plan.max_reachable_km,
        "feasible": plan.feasible,
        "status": plan.status.value,
        "status_label": plan.status.label,
        "progress_ratio": round(plan.progress_ratio, 4),
        "recommended_daily_km": plan.recommended_daily_km,
        "scenarios": [
            {
                "per_day_km": s.per_day_km,
                "days": s.days,
                "finish": iso(s.finish),
                "slack_days": s.slack_days,
                "feasible": s.feasible,
                "planned_total_km": s.planned_total_km,
                "avg_per_run_km": s.avg_per_run_km,
            }
            for s in plan.scenarios
        ],
        "schedule": [
            {"day": r.day.isoformat(), "km": r.km, "minutes": r.minutes} for r in plan.schedule
        ],
        "warnings": list(plan.warnings),
        "source": plan.source,
        "has_data": plan.has_data,
    }


if __name__ == "__main__":
    raise SystemExit(main())
