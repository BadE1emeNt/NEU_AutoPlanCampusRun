"""打开指定页面并保持窗口，方便人工/截图检查。

用法：python tools/ui_preview.py <dashboard|records|connection|help> [数据目录] [滚动比例0-1]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from campusrun.config import AppPaths  # noqa: E402
from campusrun.service import CampusRunService  # noqa: E402
from campusrun.ui.app import CampusRunApp  # noqa: E402
from campusrun.ui.theme import enable_dpi_awareness  # noqa: E402


def main() -> int:
    page = sys.argv[1] if len(sys.argv) > 1 else "dashboard"
    home = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / ".dev-home"
    scroll = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    enable_dpi_awareness()
    app = CampusRunApp(CampusRunService(AppPaths(home)))
    app.show_page(page)
    if scroll:
        app.update_idletasks()
        scroller = getattr(app.pages[page], "scroll", None)
        if scroller is not None:
            scroller.canvas.yview_moveto(scroll)
        app.update_idletasks()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
