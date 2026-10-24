"""账号密码 / 体育平台会话的本地安全存储（DPAPI）。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..config import AppPaths
from ..errors import ConfigError, SecretError
from ..secrets import protect_bytes, unprotect_bytes
from ..storage import atomic_write_bytes
from .sports import SportsSession

_SESSION_MAGIC = b"CRNS1\n"
_CRED_MAGIC = b"CRNC1\n"
_PLAIN_MAGIC = b"CRNP1\n"


@dataclass
class Credentials:
    username: str
    password: str

    def to_dict(self) -> dict[str, str]:
        return {"username": self.username, "password": self.password}

    @classmethod
    def from_dict(cls, data: dict) -> "Credentials":
        return cls(
            username=str(data.get("username") or ""),
            password=str(data.get("password") or ""),
        )


class _ProtectedFile:
    def __init__(self, path, magic: bytes):
        self.path = path
        self.magic = magic

    def save(self, payload: dict) -> bool:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            blob = protect_bytes(data)
            content = self.magic + blob
            secure = True
        except SecretError:
            content = _PLAIN_MAGIC + data
            secure = False
        atomic_write_bytes(self.path, content)
        return secure

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        raw = self.path.read_bytes()
        if raw.startswith(self.magic):
            try:
                data = unprotect_bytes(raw[len(self.magic) :])
            except SecretError as exc:
                raise ConfigError(str(exc)) from exc
        elif raw.startswith(_PLAIN_MAGIC):
            data = raw[len(_PLAIN_MAGIC) :]
        else:
            raise ConfigError("账号文件格式无法识别，请重新登录。")
        try:
            payload = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ConfigError(f"账号文件内容损坏：{exc}") from exc
        if not isinstance(payload, dict):
            raise ConfigError("账号文件内容损坏。")
        return payload

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


class NeuStore:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        self._session = _ProtectedFile(paths.sports_session_file, _SESSION_MAGIC)
        self._credentials = _ProtectedFile(paths.credentials_file, _CRED_MAGIC)

    # -- session -----------------------------------------------------
    def save_session(self, session: SportsSession) -> bool:
        return self._session.save({"version": 1, "session": session.to_dict()})

    def load_session(self) -> SportsSession | None:
        payload = self._session.load()
        if not payload or not isinstance(payload.get("session"), dict):
            return None
        session = SportsSession.from_dict(payload["session"])
        return session if session.is_complete() else None

    def clear_session(self) -> None:
        self._session.clear()

    def session_encrypted(self) -> bool:
        return self._is_encrypted(self.paths.sports_session_file, _SESSION_MAGIC)

    # -- credentials -------------------------------------------------
    def save_credentials(self, username: str, password: str) -> bool:
        return self._credentials.save(
            {"version": 1, "credentials": Credentials(username, password).to_dict()}
        )

    def load_credentials(self) -> Credentials | None:
        payload = self._credentials.load()
        if not payload or not isinstance(payload.get("credentials"), dict):
            return None
        credentials = Credentials.from_dict(payload["credentials"])
        if not credentials.username or not credentials.password:
            return None
        return credentials

    def clear_credentials(self) -> None:
        self._credentials.clear()

    def credentials_encrypted(self) -> bool:
        return self._is_encrypted(self.paths.credentials_file, _CRED_MAGIC)

    @staticmethod
    def _is_encrypted(path, magic: bytes) -> bool:
        try:
            with path.open("rb") as handle:
                return handle.read(len(magic)) == magic
        except OSError:
            return False
