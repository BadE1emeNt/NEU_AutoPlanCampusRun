"""应用服务层：把配置、连接、抓包数据源与规划算法粘在一起。

GUI 和 CLI 都只依赖这一层，不直接碰文件与网络细节。
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .analysis import PlanResult, Progress, build_plan
from .config import (
    AppConfig,
    AppPaths,
    ConnectionStore,
    SummaryCache,
    describe_age,
)
from .errors import CampusRunError, ConfigError, ProviderError
from .models import CapturedRequest, FieldMapping, HttpConnection, RunSummary
from .providers import HttpProvider, MockProvider
from .providers.autodetect import detect, summary_from_payload

LOG = logging.getLogger("campusrun")


def configure_logging(paths: AppPaths, verbose: bool = False) -> None:
    LOG.setLevel(logging.DEBUG if verbose else logging.INFO)
    if any(isinstance(h, logging.FileHandler) for h in LOG.handlers):
        return
    try:
        from logging.handlers import RotatingFileHandler

        handler = RotatingFileHandler(
            paths.logs_dir / "app.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        LOG.addHandler(handler)
    except OSError:
        LOG.addHandler(logging.NullHandler())


class CampusRunService:
    def __init__(self, paths: AppPaths | None = None):
        self.paths = (paths or AppPaths.default()).ensure()
        configure_logging(self.paths)
        self.config = AppConfig()
        self.connection: HttpConnection | None = None
        self.summary: RunSummary | None = None
        self.startup_warnings: list[str] = []
        self._connection_store = ConnectionStore(self.paths)
        self._cache = SummaryCache(self.paths)
        self.reload()

    # ---- 初始化 / 持久化 ------------------------------------------
    def reload(self) -> None:
        self.startup_warnings.clear()
        try:
            self.config = AppConfig.load(self.paths)
        except ConfigError as exc:
            LOG.warning("配置读取失败，使用默认值：%s", exc)
            self.startup_warnings.append(str(exc))
            self.config = AppConfig()

        if self._connection_store.exists():
            try:
                self.connection = self._connection_store.load()
            except ConfigError as exc:
                LOG.warning("连接读取失败：%s", exc)
                self.startup_warnings.append(str(exc))
                self.connection = None
        else:
            self.connection = None

        if self.config.demo_mode:
            self.summary = MockProvider().fetch()
        else:
            self.summary = self._cache.load()

    def save_config(self) -> None:
        # 先做一次规则校验，避免把非法值写进文件
        self.config.to_plan_settings()
        self.config.save(self.paths)

    def update_config(self, **changes: Any) -> None:
        for key, value in changes.items():
            if not hasattr(self.config, key):
                raise ConfigError(f"未知配置项：{key}")
            setattr(self.config, key, value)
        self.save_config()
        if self.config.demo_mode:
            self.summary = MockProvider().fetch()
        self.recompute()

    def set_demo_mode(self, enabled: bool) -> None:
        self.config.demo_mode = bool(enabled)
        self.save_config()
        if enabled:
            self.summary = MockProvider().fetch()
        else:
            cached = self._cache.load()
            self.summary = cached
        self.recompute()

    def recompute(self) -> PlanResult:
        if self.summary is not None:
            progress = Progress.from_summary(self.summary)
        else:
            progress = Progress()
        return build_plan(progress, self.config.to_plan_settings())

    def plan(self) -> PlanResult:
        return self.recompute()

    # ---- 数据获取 -------------------------------------------------
    def refresh(self) -> RunSummary:
        if self.config.demo_mode:
            summary = MockProvider().fetch()
            self.summary = summary
            LOG.info("已刷新演示数据：%.1f km / %d 次", summary.completed_km, summary.completed_runs)
            return summary
        if self.connection is None:
            raise ProviderError("还没有配置真实接口。请到“连接”页粘贴抓包得到的 cURL。")
        provider = HttpProvider(self.connection, count_mode=self.config.count_mode)
        summary = provider.fetch()
        self.summary = summary
        self._cache.save(summary)
        LOG.info("已刷新真实数据：%.1f km / %d 次", summary.completed_km, summary.completed_runs)
        return summary

    @property
    def is_demo(self) -> bool:
        return self.config.demo_mode

    @property
    def has_connection(self) -> bool:
        return self.connection is not None

    @property
    def connection_encrypted(self) -> bool:
        return self._connection_store.is_encrypted()

    def source_text(self) -> str:
        if self.config.demo_mode:
            return "演示数据"
        if self.summary is None:
            return "尚未获取"
        return f"{self.summary.provider} · {describe_age(self.summary.fetched_at)}"

    def save_connection(self, request: CapturedRequest, mapping: FieldMapping, label: str = "") -> bool:
        connection = HttpConnection(request=request, mapping=mapping, label=label)
        # 保存前先验证一次映射能不能跑通（不联网，只解析最近一次预览缓存；失败也不阻止保存）
        secure = self._connection_store.save(connection)
        self.connection = connection
        self.config.demo_mode = False
        self.save_config()
        LOG.info("已保存连接：%s（%s）", request.host, "DPAPI 加密" if secure else "明文")
        return secure

    def clear_connection(self) -> None:
        self._connection_store.clear()
        self.connection = None
        self._cache.clear()
        self.summary = None
        self.config.demo_mode = True
        self.save_config()
        LOG.info("已清除连接")

    def detect_from_payload(self, payload: Any) -> tuple[FieldMapping, str]:
        detection = detect(payload)
        return detection.mapping, detection.notes

    def adopt_summary(self, summary: RunSummary) -> None:
        """把刚由抓包响应解析出的汇总直接采用，避免再请求一次。"""

        self.summary = summary
        self._cache.save(summary)
        self.config.demo_mode = False
        self.save_config()

    def preview_from_payload(self, payload: Any, mapping: FieldMapping) -> RunSummary:
        return summary_from_payload(payload, mapping, provider=self.connection_host, count_mode=self.config.count_mode)

    @property
    def connection_host(self) -> str:
        return self.connection.request.host if self.connection else "抓包接口"

    # ---- 导出 -----------------------------------------------------
    def export_csv(self, summary: RunSummary | None = None) -> Path:
        summary = summary or self.summary
        if summary is None or not summary.records:
            raise CampusRunError("没有可导出的跑步记录")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.paths.exports_dir / f"campusrun-{stamp}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["日期", "星期", "里程(km)", "用时(秒)", "配速(秒/km)", "有效", "记录ID"])
            weekdays = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
            for record in sorted(summary.records, key=lambda r: (r.day, r.start_time or datetime.min)):
                pace = record.pace_sec_per_km
                writer.writerow(
                    [
                        record.day.isoformat(),
                        weekdays[record.day.weekday()],
                        f"{record.distance_km:.2f}",
                        record.duration_sec or "",
                        f"{pace:.0f}" if pace else "",
                        "是" if record.valid else "否",
                        record.run_id or "",
                    ]
                )
        LOG.info("已导出 CSV：%s", path)
        return path
