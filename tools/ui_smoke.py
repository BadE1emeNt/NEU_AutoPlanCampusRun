"""GUI 冒烟测试：创建窗口、切换所有页面、打开计划弹窗，然后退出。

用法：
    python tools/ui_smoke.py [数据目录]
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from campusrun.config import AppPaths  # noqa: E402
from campusrun.service import CampusRunService  # noqa: E402
from campusrun.ui.app import CampusRunApp  # noqa: E402
from campusrun.ui.plan_dialog import PlanDialog  # noqa: E402
from campusrun.ui.theme import enable_dpi_awareness  # noqa: E402


def main() -> int:
    home = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".dev-home"
    enable_dpi_awareness()
    service = CampusRunService(AppPaths(home))
    app = CampusRunApp(service, show_onboarding=False)
    try:
        app.update_idletasks()
        app.update()
        for name in ("records", "connection", "help", "dashboard"):
            app.show_page(name)
            app.update_idletasks()
            app.update()
            print(f"page ok: {name}")
        dialog = PlanDialog(app, app)
        app.update_idletasks()
        app.update()
        dialog._select(3.0)
        app.update_idletasks()
        app.update()
        rows = dialog.tree.get_children()
        print(f"plan rows: {len(rows)}")
        dialog._close()
        app.update_idletasks()
        app.update()
        print("plan dialog ok")
        print("SMOKE OK")
        return 0
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        try:
            app.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
