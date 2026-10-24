"""打开主窗口与完整计划弹窗，方便截图检查。

用法：python tools/ui_plan_preview.py [数据目录]
"""

from __future__ import annotations

import sys
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
    app = CampusRunApp(CampusRunService(AppPaths(home)))
    app.show_page("dashboard")
    app.update_idletasks()
    app.update()
    dialog = PlanDialog(app, app)
    dialog.update_idletasks()
    dialog.update()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
