"""端到端 GUI 流程测试：粘贴 cURL → 抓取 → 自动识别 → 保存 → 规划更新。

用本地 HTTP 服务器模拟校园接口，不会访问外网。
"""

from __future__ import annotations

import json
import shutil
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from campusrun.config import AppPaths  # noqa: E402
from campusrun.service import CampusRunService  # noqa: E402
from campusrun.ui.app import CampusRunApp  # noqa: E402
from campusrun.ui import connection as connection_module  # noqa: E402
from campusrun.ui.theme import enable_dpi_awareness  # noqa: E402

PAYLOAD = {
    "code": 0,
    "data": {
        "list": [
            {"runDate": "2026-10-20 19:30:00", "distance": 3200, "duration": 1200, "valid": 1},
            {"runDate": "2026-10-22 20:00:00", "distance": 2000, "duration": 760, "valid": 1},
        ]
    },
}


class Server:
    def __init__(self):
        self.last_auth = ""
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                owner.last_auth = self.headers.get("Authorization", "")
                body = json.dumps(PAYLOAD).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address
        return f"http://{host}:{port}/api/run?page=1"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def main() -> int:
    home = ROOT / "tests" / ".tmp" / f"e2e-{uuid.uuid4().hex[:8]}"
    home.mkdir(parents=True)
    # 避免弹窗阻塞自动化
    connection_module.messagebox.showinfo = lambda *a, **k: None
    connection_module.messagebox.showerror = lambda *a, **k: print("showerror:", a)

    errors: list[BaseException] = []
    with Server() as server:
        enable_dpi_awareness()
        service = CampusRunService(AppPaths(home))
        app = CampusRunApp(service)
        try:
            app.update()
            page = app.pages["connection"]
            page.curl_text.insert("1.0", f"curl '{server.url}' -H 'Authorization: Bearer e2e-token'")
            page._parse_and_fetch()
            deadline = time.time() + 15
            while page._payload is None and time.time() < deadline:
                app.update()
                time.sleep(0.02)
            if page._payload is None:
                raise RuntimeError("抓取超时")
            if page._mapping is None:
                raise RuntimeError("未自动识别字段")
            if server.last_auth != "Bearer e2e-token":
                raise RuntimeError(f"鉴权头未透传：{server.last_auth!r}")

            page._save()
            app.update()
            if service.config.demo_mode:
                raise RuntimeError("保存后仍处于演示模式")
            if abs(service.summary.completed_km - 5.2) > 1e-6:
                raise RuntimeError(f"汇总里程错误：{service.summary.completed_km}")
            if service.summary.completed_runs != 2:
                raise RuntimeError("汇总次数错误")
            if not service.connection_encrypted:
                raise RuntimeError("连接未加密")
            plan = service.plan()
            if abs(plan.completed_km - 5.2) > 1e-6:
                raise RuntimeError("规划未使用真实数据")
            print("GUI flow: parse/fetch/detect/save ok")

            reloaded = CampusRunService(AppPaths(home))
            if reloaded.connection is None:
                raise RuntimeError("重启后连接未加载")
            if reloaded.config.demo_mode:
                raise RuntimeError("重启后仍为演示模式")
            summary = reloaded.refresh()
            if abs(summary.completed_km - 5.2) > 1e-6:
                raise RuntimeError("重启后刷新失败")
            print("GUI flow: reload/refresh ok")
            print("E2E OK")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            try:
                app.destroy()
            except Exception:
                pass

    shutil.rmtree(home, ignore_errors=True)
    if errors:
        for error in errors:
            print(f"E2E FAILED: {type(error).__name__}: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
