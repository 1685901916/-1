from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Iterator


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def natural_sort_key(value: str) -> list[tuple[int, object]]:
    normalized = str(value).replace("\\", "/")
    parts: list[tuple[int, object]] = []
    cursor = 0
    for match in _NUMBER_RE.finditer(normalized):
        if match.start() > cursor:
            parts.append((1, normalized[cursor:match.start()].lower()))
        token = match.group(0)
        if "." in token:
            parts.extend((0, int(piece)) for piece in token.split("."))
        else:
            parts.append((0, int(token)))
        cursor = match.end()
    if cursor < len(normalized):
        parts.append((1, normalized[cursor:].lower()))
    return parts


def iter_image_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*"), key=lambda item: natural_sort_key(str(item))):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            yield path


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def path_size_mb(path: Path) -> float:
    if path.is_file():
        return path.stat().st_size / (1024 * 1024)
    total = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    return total / (1024 * 1024)


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
