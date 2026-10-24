"""PyInstaller entry point for the Windows release.

Build with tools/build_exe.ps1; running the resulting CampusRun.exe without
arguments opens the GUI, exactly like run.cmd.
"""

from __future__ import annotations

import multiprocessing
import sys

from campusrun.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main(sys.argv[1:]))
