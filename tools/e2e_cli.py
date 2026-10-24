"""CLI 端到端测试：import-curl → plan --json，用本地 HTTP 服务器。"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from campusrun.cli import main  # noqa: E402
from campusrun.config import AppPaths  # noqa: E402
from campusrun.service import CampusRunService  # noqa: E402

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
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
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
        return f"http://{host}:{port}/api/run"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def run_cli(args: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = main(args)
    return code, buffer.getvalue()


def main_test() -> int:
    home = ROOT / "tests" / ".tmp" / f"cli-{uuid.uuid4().hex[:8]}"
    home.mkdir(parents=True)
    curl = home / "capture.txt"
    try:
        with Server() as server:
            curl.write_text(
                f"curl '{server.url}' -H 'Authorization: Bearer cli-token' -H 'Accept: application/json'",
                encoding="utf-8",
            )
            code, output = run_cli(["--home", str(home), "import-curl", "--file", str(curl)])
            if code != 0:
                print(output)
                raise RuntimeError(f"import-curl 退出码 {code}")
            if "已保存连接" not in output or "DPAPI" not in output:
                print(output)
                raise RuntimeError("import-curl 输出不符合预期")
            print("CLI import: ok")

            service = CampusRunService(AppPaths(home))
            if service.connection is None:
                raise RuntimeError("CLI 保存后连接未加载")
            if round(service.summary.completed_km, 2) != 5.2:
                raise RuntimeError(f"缓存里程错误：{service.summary.completed_km}")
            if service.config.demo_mode:
                raise RuntimeError("import 后仍是演示模式")
            print("CLI cache: ok")

            code, output = run_cli(["--home", str(home), "plan", "--json"])
            if code != 0:
                print(output)
                raise RuntimeError(f"plan 退出码 {code}")
            plan = json.loads(output)
            if abs(plan["completed_km"] - 5.2) > 1e-6:
                raise RuntimeError("plan 未使用真实数据")
            if plan["target_km"] != 96:
                raise RuntimeError("plan 目标错误")
            print("CLI plan: ok")

            code, output = run_cli(["--home", str(home), "doctor"])
            if code != 0 or "DPAPI" not in output:
                print(output)
                raise RuntimeError("doctor 失败")
            print("CLI doctor: ok")
        print("CLI E2E OK")
        return 0
    finally:
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main_test())
