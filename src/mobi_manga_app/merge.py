from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from .repack import export_cbz, export_pdf, export_zip, run_kcc
from .tools import discover_tools
from .unpack import unpack_and_collect
from .utils import iter_image_files


def _merge_name(source_paths: list[Path]) -> str:
    if not source_paths:
        return f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if len(source_paths) == 1:
        return source_paths[0].stem
    return f"{source_paths[0].stem}_plus_{len(source_paths) - 1}"


def merge_sources(
    source_paths: list[Path],
    output_dir: Path,
    output_formats: list[str],
    *,
    target_name: str | None = None,
) -> dict[str, object]:
    if len(source_paths) < 2:
        raise ValueError("Select at least two source files or folders to merge.")

    tools = discover_tools()
    output_dir.mkdir(parents=True, exist_ok=True)
    merge_name = target_name or _merge_name(source_paths)
    merge_root = output_dir / merge_name
    if merge_root.exists():
        shutil.rmtree(merge_root, ignore_errors=True)
    pages_dir = merge_root / "pages_merged"
    pages_dir.mkdir(parents=True, exist_ok=True)

    logs: list[str] = []
    page_index = 1

    with tempfile.TemporaryDirectory(prefix="manga_merge_") as temp_dir:
        temp_root = Path(temp_dir)
        for source_order, source_path in enumerate(source_paths, start=1):
            logs.append(f"merge source {source_order}: {source_path}")
            source_workspace = temp_root / f"source_{source_order:02d}"
            result = unpack_and_collect(
                source_path,
                source_workspace / "unpacked",
                source_workspace / "pages",
                tools.kindleunpack,
            )
            for image_path in iter_image_files(result.pages_dir):
                target = pages_dir / f"page_{page_index:04d}{image_path.suffix.lower()}"
                shutil.copy2(image_path, target)
                page_index += 1

    if page_index == 1:
        raise RuntimeError("Merge produced no pages.")

    selected_formats = set(output_formats or ["cbz"])
    exported_files: list[str] = []

    if "cbz" in selected_formats:
        exported_files.append(str(export_cbz(pages_dir, merge_root / f"{merge_name}.cbz")))
    if "zip" in selected_formats:
        exported_files.append(str(export_zip(pages_dir, merge_root / f"{merge_name}.zip")))
    if "pdf" in selected_formats:
        exported_files.append(str(export_pdf(pages_dir, merge_root / f"{merge_name}.pdf")))

    if {"epub", "mobi"} & selected_formats:
        if not tools.kcc.available:
            raise RuntimeError("KCC is required for EPUB or MOBI merge export.")
        extra_args: list[str] = []
        if "mobi" in selected_formats and "epub" not in selected_formats:
            extra_args = ["--mobi"]
        run_kcc(tools.kcc, pages_dir, merge_root, extra_args=extra_args)
        if "epub" in selected_formats:
            exported_files.extend(str(path) for path in merge_root.glob("*.epub"))
        if "mobi" in selected_formats:
            exported_files.extend(str(path) for path in merge_root.glob("*.mobi"))

    manifest = {
        "merge_name": merge_name,
        "sources": [str(path) for path in source_paths],
        "page_count": page_index - 1,
        "output_dir": str(merge_root),
        "output_formats": sorted(selected_formats),
        "files": exported_files,
        "output_files": exported_files,
        "logs": logs,
    }
    manifest_path = merge_root / "merge_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest"] = str(manifest_path)
    return manifest
