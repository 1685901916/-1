from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Iterator


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}


def natural_sort_key(value: str) -> list[object]:
    return [int(chunk) if chunk.isdigit() else chunk.lower() for chunk in re.split(r"(\d+)", value)]


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
