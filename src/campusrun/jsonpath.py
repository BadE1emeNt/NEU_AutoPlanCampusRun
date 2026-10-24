"""极简 JSON 路径取值：支持 ``data.list``、``data.rows[0].items``、``["key"]``。"""

from __future__ import annotations

import json
from typing import Any, Iterator

_MISSING = object()


def split_path(path: str) -> list[str | int]:
    text = (path or "").strip()
    if text.startswith("$"):
        text = text[1:].lstrip(".")
    if not text or text == ".":
        return []
    parts: list[str | int] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == ".":
            index += 1
            continue
        if char == "[":
            if index + 1 < length and text[index + 1] in ("'", '"'):
                quote = text[index + 1]
                end = text.find(quote + "]", index + 2)
                if end < 0:
                    raise ValueError(f"JSON 路径缺少右括号：{path}")
                parts.append(text[index + 2 : end])
                index = end + 2
            else:
                end = text.find("]", index + 1)
                if end < 0:
                    raise ValueError(f"JSON 路径缺少右括号：{path}")
                token = text[index + 1 : end].strip()
                parts.append(int(token) if token.lstrip("-").isdigit() else token)
                index = end + 1
            continue
        end = index
        while end < length and text[end] not in ".[":
            end += 1
        token = text[index:end].strip()
        if token:
            parts.append(token)
        index = end
    return parts


def get_path(obj: Any, path: str, default: Any = None) -> Any:
    if path is None or path == "":
        return obj
    current = obj
    try:
        parts = split_path(path)
    except ValueError:
        return default
    for part in parts:
        if isinstance(part, int):
            if isinstance(current, list) and -len(current) <= part < len(current):
                current = current[part]
            else:
                return default
        else:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
    return current


def walk_paths(obj: Any, prefix: str = "", depth: int = 0, max_depth: int = 8) -> Iterator[tuple[str, Any]]:
    """遍历所有节点，产出 (路径, 值)；用于自动识别记录数组与汇总字段。"""

    if depth > max_depth:
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path, value
            yield from walk_paths(value, path, depth + 1, max_depth)
    elif isinstance(obj, list):
        yield prefix, obj
        for index, value in enumerate(obj[:5]):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            yield from walk_paths(value, path, depth + 1, max_depth)


def preview_json(obj: Any, limit: int = 6000) -> str:
    try:
        text = json.dumps(obj, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        text = str(obj)
    if len(text) > limit:
        return text[:limit] + f"\n…（已截断，共 {len(text)} 字符）"
    return text
