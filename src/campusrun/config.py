"""配置、抓包连接（DPAPI 加密）与摘要缓存。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .analysis import PlanSettings
from .errors import ConfigError, SecretError
from .models import HttpConnection, RunSummary
from .secrets import protect_bytes, unprotect_bytes
from .storage import atomic_write_bytes, atomic_write_text, ensure_dir, read_json

CONFIG_VERSION = 1
_PROTECTED_MAGIC = b"CRDP1\n"
_PLAIN_MAGIC = b"CRPL1\n"


def default_deadline(today: date | None = None) -> date:
    """按学期给一个合理默认值：秋季到次年 1 月 10 日，春季到 6 月 30 日。"""

    today = today or date.today()
    if today.month == 1:
        return date(today.year, 1, 10)
    if today.month <= 7:
        return date(today.year, 6, 30)
    return date(today.year + 1, 1, 10)


@dataclass(frozen=True)
class AppPaths:
    home: Path

    @classmethod
    def default(cls) -> "AppPaths":
        override = os.environ.get("CAMPUSRUN_HOME")
        if override:
            return cls(Path(override).expanduser().resolve())
        appdata = os.environ.get("APPDATA")
        if appdata:
            return cls(Path(appdata) / "CampusRun")
        return cls(Path.home() / ".campusrun")

    @property
    def config_file(self) -> Path:
        return self.home / "config.json"

    @property
    def connection_file(self) -> Path:
        return self.home / "connection.dat"

    @property
    def sports_session_file(self) -> Path:
        return self.home / "sports_session.dat"

    @property
    def credentials_file(self) -> Path:
        return self.home / "credentials.dat"

    @property
    def cache_file(self) -> Path:
        return self.home / "cache" / "summary.json"

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"

    @property
    def exports_dir(self) -> Path:
        return self.home / "exports"

    def ensure(self) -> "AppPaths":
        ensure_dir(self.home)
        ensure_dir(self.home / "cache")
        ensure_dir(self.logs_dir)
        ensure_dir(self.exports_dir)
        return self


@dataclass
class AppConfig:
    target_km: float = 96.0
    deadline: date = field(default_factory=default_deadline)
    pace_min_per_km: float = 6.5
    min_run_km: float = 2.0
    max_run_km: float = 5.0
    rest_weekdays: list[int] = field(default_factory=list)
    demo_mode: bool = True
    count_mode: str = "best_per_day"
    auth_mode: str = "password"
    remember_password: bool = False
    neu_username: str = ""
    window_geometry: str = ""
    last_page: str = "dashboard"

    def to_plan_settings(self) -> PlanSettings:
        return PlanSettings(
            target_km=self.target_km,
            deadline=self.deadline,
            min_run_km=self.min_run_km,
            max_run_km=self.max_run_km,
            rest_weekdays=frozenset(self.rest_weekdays),
            pace_min_per_km=self.pace_min_per_km,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": CONFIG_VERSION,
            "target_km": self.target_km,
            "deadline": self.deadline.isoformat(),
            "pace_min_per_km": self.pace_min_per_km,
            "min_run_km": self.min_run_km,
            "max_run_km": self.max_run_km,
            "rest_weekdays": sorted(set(self.rest_weekdays)),
            "demo_mode": self.demo_mode,
            "count_mode": self.count_mode,
            "auth_mode": self.auth_mode,
            "remember_password": self.remember_password,
            "neu_username": self.neu_username,
            "window_geometry": self.window_geometry,
            "last_page": self.last_page,
        }

    @classmethod
    def load(cls, paths: AppPaths) -> "AppConfig":
        path = paths.config_file
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ConfigError(f"配置文件读取失败：{path}\n{exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError(f"配置文件格式不正确：{path}")
        return cls.from_dict(raw, path)

    @classmethod
    def from_dict(cls, raw: dict[str, Any], path: Path | None = None) -> "AppConfig":
        where = f"（{path}）" if path else ""

        def positive(name: str, default: float, low: float, high: float) -> float:
            value = raw.get(name, default)
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"配置项 {name} 不是数字{where}") from exc
            if not (low <= number <= high):
                raise ConfigError(f"配置项 {name} 超出范围 {low}–{high}{where}")
            return number

        target = positive("target_km", 96.0, 1.0, 1000.0)
        pace = positive("pace_min_per_km", 6.5, 2.0, 20.0)
        min_run = positive("min_run_km", 2.0, 0.1, 50.0)
        max_run = positive("max_run_km", 5.0, 0.1, 100.0)
        if max_run < min_run:
            raise ConfigError(f"单次最多里程不能小于单次最少里程{where}")

        deadline_raw = raw.get("deadline")
        if isinstance(deadline_raw, str) and deadline_raw:
            try:
                deadline = date.fromisoformat(deadline_raw[:10])
            except ValueError as exc:
                raise ConfigError(f"截止日期格式应为 YYYY-MM-DD{where}") from exc
        else:
            deadline = default_deadline()

        rest_raw = raw.get("rest_weekdays") or []
        if not isinstance(rest_raw, list):
            raise ConfigError(f"rest_weekdays 必须是数组{where}")
        rest: set[int] = set()
        for item in rest_raw:
            try:
                day = int(item)
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"休息日取值不合法{where}") from exc
            if not 0 <= day <= 6:
                raise ConfigError(f"休息日必须在 0–6 之间{where}")
            rest.add(day)

        count_mode = str(raw.get("count_mode") or "best_per_day")
        if count_mode not in ("best_per_day", "sum"):
            count_mode = "best_per_day"

        geometry = str(raw.get("window_geometry") or "")
        last_page = str(raw.get("last_page") or "dashboard")
        auth_mode = str(raw.get("auth_mode") or "password")
        if auth_mode not in ("curl", "password"):
            auth_mode = "password"
        return cls(
            target_km=target,
            deadline=deadline,
            pace_min_per_km=pace,
            min_run_km=min_run,
            max_run_km=max_run,
            rest_weekdays=sorted(rest),
            demo_mode=bool(raw.get("demo_mode", True)),
            count_mode=count_mode,
            auth_mode=auth_mode,
            remember_password=bool(raw.get("remember_password", False)),
            neu_username=str(raw.get("neu_username") or ""),
            window_geometry=geometry,
            last_page=last_page,
        )

    def save(self, paths: AppPaths) -> None:
        atomic_write_text(
            paths.config_file,
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
        )


class ConnectionStore:
    """连接文件：优先 DPAPI 加密；DPAPI 不可用时降级为明文并明确告知调用方。"""

    def __init__(self, paths: AppPaths):
        self.paths = paths

    def load(self) -> HttpConnection | None:
        path = self.paths.connection_file
        if not path.exists():
            return None
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ConfigError(f"连接文件读取失败：{path}\n{exc}") from exc
        if raw.startswith(_PROTECTED_MAGIC):
            try:
                payload = unprotect_bytes(raw[len(_PROTECTED_MAGIC) :])
            except SecretError as exc:
                raise ConfigError(str(exc)) from exc
        elif raw.startswith(_PLAIN_MAGIC):
            payload = raw[len(_PLAIN_MAGIC) :]
        else:
            raise ConfigError("连接文件格式无法识别，请重新粘贴 cURL 保存。")
        try:
            data = json.loads(payload.decode("utf-8"))
            return HttpConnection.from_dict(data)
        except (ValueError, UnicodeDecodeError, TypeError) as exc:
            raise ConfigError(f"连接文件内容损坏：{exc}") from exc

    def save(self, connection: HttpConnection) -> bool:
        payload = json.dumps(connection.to_dict(), ensure_ascii=False).encode("utf-8")
        try:
            blob = protect_bytes(payload)
            data = _PROTECTED_MAGIC + blob
            secure = True
        except SecretError:
            data = _PLAIN_MAGIC + payload
            secure = False
        atomic_write_bytes(self.paths.connection_file, data)
        return secure

    def is_encrypted(self) -> bool:
        try:
            with self.paths.connection_file.open("rb") as handle:
                return handle.read(len(_PROTECTED_MAGIC)) == _PROTECTED_MAGIC
        except OSError:
            return False

    def exists(self) -> bool:
        return self.paths.connection_file.exists()

    def clear(self) -> None:
        try:
            self.paths.connection_file.unlink()
        except FileNotFoundError:
            pass


class SummaryCache:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    def save(self, summary: RunSummary) -> None:
        payload = {"version": CONFIG_VERSION, "summary": summary.to_dict()}
        atomic_write_text(
            self.paths.cache_file,
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        )

    def load(self) -> RunSummary | None:
        raw = read_json(self.paths.cache_file)
        if not isinstance(raw, dict) or not isinstance(raw.get("summary"), dict):
            return None
        try:
            return RunSummary.from_dict(raw["summary"])
        except (ValueError, TypeError):
            return None

    def clear(self) -> None:
        try:
            self.paths.cache_file.unlink()
        except FileNotFoundError:
            pass


def config_summary(config: AppConfig) -> str:
    rest = "、".join(("周一", "周二", "周三", "周四", "周五", "周六", "周日")[i] for i in config.rest_weekdays)
    demo = "演示数据" if config.demo_mode else "真实接口"
    return (
        f"目标 {config.target_km:g} km · 截止 {config.deadline.isoformat()} · "
        f"配速 {config.pace_min_per_km:g} min/km · 休息日 {rest or '无'} · {demo}"
    )


def describe_age(fetched_at: datetime) -> str:
    delta = datetime.now() - fetched_at
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "刚刚"
    if minutes < 60:
        return f"{minutes} 分钟前"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} 小时前"
    return f"{hours // 24} 天前"
