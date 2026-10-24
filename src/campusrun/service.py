"""应用服务层：把配置、连接、抓包数据源与规划算法粘在一起。

GUI 和 CLI 都只依赖这一层，不直接碰文件与网络细节。
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

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
from .neu.cas import CasLoginClient, SmsChallenge
from .neu.sports import SportsClient, SportsSession, SportsSessionExpired
from .neu.store import Credentials, NeuStore
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
        self.sports_session: SportsSession | None = None
        self.credentials: Credentials | None = None
        self.summary: RunSummary | None = None
        self.startup_warnings: list[str] = []
        self.last_cache_error: str | None = None
        self._connection_store = ConnectionStore(self.paths)
        self._neu_store = NeuStore(self.paths)
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

        try:
            self.sports_session = self._neu_store.load_session()
        except ConfigError as exc:
            LOG.warning("体育平台会话读取失败：%s", exc)
            self.startup_warnings.append(str(exc))
            self.sports_session = None

        try:
            self.credentials = self._neu_store.load_credentials()
        except ConfigError as exc:
            LOG.warning("账号密码读取失败：%s", exc)
            self.startup_warnings.append(str(exc))
            self.credentials = None

        if self.config.demo_mode:
            self.summary = MockProvider().fetch()
        else:
            self.summary = self._cache.load()

    def save_config(self) -> None:
        # 先做一次规则校验，避免把非法值写进文件
        self.config.to_plan_settings()
        self.config.save(self.paths)

    def _save_cache(self, summary: RunSummary) -> None:
        """缓存是可选加速；写不进去不应该让整次刷新失败。"""

        try:
            self._cache.save(summary)
            self.last_cache_error = None
        except OSError as exc:
            self.last_cache_error = str(exc)
            LOG.warning("摘要缓存写入失败（本次数据仍然可用）：%s", exc)

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
    def refresh(self, sms_provider: Callable[[SmsChallenge], str] | None = None) -> RunSummary:
        if self.config.demo_mode:
            summary = MockProvider().fetch()
            self.summary = summary
            LOG.info("已刷新演示数据：%.1f km / %d 次", summary.completed_km, summary.completed_runs)
            return summary
        if self.config.auth_mode == "password" or (
            self.sports_session is not None and self.connection is None
        ):
            return self._refresh_neu(sms_provider)
        if self.connection is None:
            raise ProviderError("还没有配置真实接口。请到“连接”页登录或粘贴 cURL。")
        provider = HttpProvider(self.connection, count_mode=self.config.count_mode)
        summary = provider.fetch()
        self.summary = summary
        self._save_cache(summary)
        LOG.info("已刷新真实数据：%.1f km / %d 次", summary.completed_km, summary.completed_runs)
        return summary

    def _refresh_neu(
        self, sms_provider: Callable[[SmsChallenge], str] | None
    ) -> RunSummary:
        if self.sports_session is None:
            if self.credentials is None:
                raise ProviderError("登录态已失效，请到“连接”页重新输入账号密码。")
            self._login_neu_session(
                self.credentials.username,
                self.credentials.password,
                sms_provider,
            )
        assert self.sports_session is not None
        try:
            fetch = SportsClient(self.sports_session).fetch()
        except SportsSessionExpired:
            if self.credentials is None:
                raise ProviderError("体育平台登录态已过期，请重新输入账号密码。") from None
            session = self._login_neu_session(
                self.credentials.username,
                self.credentials.password,
                sms_provider,
            )
            fetch = SportsClient(session).fetch()
        self.summary = fetch.summary
        self._save_cache(fetch.summary)
        self._neu_store.save_session(self.sports_session)
        LOG.info("已刷新校园乐跑：%.1f km / %d 次", fetch.summary.completed_km, fetch.summary.completed_runs)
        return fetch.summary

    def _login_neu_session(
        self,
        username: str,
        password: str,
        sms_provider: Callable[[SmsChallenge], str] | None = None,
    ) -> SportsSession:
        result = CasLoginClient().login(username, password, sms_provider=sms_provider)
        self.sports_session = result.session
        self._neu_store.save_session(result.session)
        LOG.info("统一身份认证登录成功：uid=%s", result.session.uid)
        return result.session

    def login_neu(
        self,
        username: str,
        password: str,
        remember_password: bool = False,
        sms_provider: Callable[[SmsChallenge], str] | None = None,
    ) -> RunSummary:
        username = username.strip()
        if not username:
            raise ProviderError("请输入学号。")
        if not password and self.credentials and self.credentials.username == username:
            password = self.credentials.password
        if not password:
            raise ProviderError("请输入密码。")
        session = self._login_neu_session(username, password, sms_provider)
        fetch = SportsClient(session).fetch()
        self.summary = fetch.summary
        self._save_cache(fetch.summary)
        self._neu_store.save_session(self.sports_session or session)
        self.config.auth_mode = "password"
        self.config.demo_mode = False
        self.config.remember_password = bool(remember_password)
        self.config.neu_username = username
        self.save_config()
        if remember_password:
            self._neu_store.save_credentials(username, password)
            self.credentials = Credentials(username, password)
        else:
            self._neu_store.clear_credentials()
            self.credentials = None
        LOG.info("校园乐跑登录成功：%.1f km / %d 次", fetch.summary.completed_km, fetch.summary.completed_runs)
        return fetch.summary

    def test_login_neu(
        self,
        username: str,
        password: str,
        sms_provider: Callable[[SmsChallenge], str] | None = None,
    ) -> RunSummary:
        """只验证账号密码/接口，不保存密码、token、配置或缓存。"""

        username = username.strip()
        if not username:
            raise ProviderError("请输入学号。")
        if not password:
            raise ProviderError("测试登录需要输入密码。")
        result = CasLoginClient().login(username, password, sms_provider=sms_provider)
        fetch = SportsClient(result.session).fetch()
        LOG.info("测试登录成功（未保存）：%.1f km / %d 次", fetch.summary.completed_km, fetch.summary.completed_runs)
        return fetch.summary

    def clear_neu_login(self, clear_credentials: bool = True) -> None:
        self._neu_store.clear_session()
        if clear_credentials:
            self._neu_store.clear_credentials()
            self.credentials = None
        self.sports_session = None
        if self.config.auth_mode == "password":
            self.config.auth_mode = "curl" if self.connection is not None else "password"
            self.save_config()
        LOG.info("已清除体育平台登录态")

    @property
    def has_neu_session(self) -> bool:
        return self.sports_session is not None

    @property
    def has_saved_credentials(self) -> bool:
        return self.credentials is not None

    @property
    def neu_session_encrypted(self) -> bool:
        return self._neu_store.session_encrypted()

    @property
    def credentials_encrypted(self) -> bool:
        return self._neu_store.credentials_encrypted()

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
        self.config.auth_mode = "curl"
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
        self._save_cache(summary)
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
