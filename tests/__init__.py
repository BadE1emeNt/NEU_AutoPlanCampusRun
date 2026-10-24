"""测试包：让 ``python -m unittest discover -s tests -t .`` 直接使用 src 布局。

注意：某些受限执行环境只允许写工作区，而且 Python 3.14 在 Windows 上创建
``mode=0o700`` 的目录时生成的访问控制会挡住沙箱令牌。因此这里不用
``tempfile.TemporaryDirectory``，而是在仓库内用默认权限创建临时目录。
"""

from __future__ import annotations

import shutil
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

_TMP = Path(__file__).resolve().parent / ".tmp"
_TMP.mkdir(parents=True, exist_ok=True)


@contextmanager
def workspace_tmp() -> Iterator[Path]:
    path = _TMP / f"case-{uuid.uuid4().hex[:10]}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
