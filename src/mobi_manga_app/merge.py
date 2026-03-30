from __future__ import annotations

import json
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from .enhance import EnhanceOptions, enhance_pages
from .repack import export_cbz, export_pdf, export_zip, run_kcc
from .tools import discover_tools
from .unpack import unpack_and_collect
from .utils import iter_image_files, reset_dir


def _extract_numeric_token(path: Path) -> str | None:
    matches = [part for part in re.findall(r"\d+", path.stem) if part]
    return matches[-1] if matches else None


def _merge_name(source_paths: list[Path]) -> str:
    if not source_paths:
        return f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if len(source_paths) == 1:
        return source_paths[0].stem
    first_token = _extract_numeric_token(source_paths[0])
    last_token = _extract_numeric_token(source_paths[-1])
    if first_token and last_token:
        return f"{first_token}_{last_token}"
    return f"{source_paths[0].stem}_{source_paths[-1].stem}"


def _next_available_merge_root(output_dir: Path, merge_name: str) -> tuple[str, Path]:
    candidate_name = merge_name
    candidate_root = output_dir / candidate_name
    suffix = 1
    while candidate_root.exists():
        candidate_name = f"{merge_name}({suffix})"
        candidate_root = output_dir / candidate_name
        suffix += 1
    return candidate_name, candidate_root


def _resolve_merge_root(output_dir: Path, merge_name: str) -> tuple[str, Path]:
    if output_dir.name == merge_name:
        return merge_name, output_dir
    return _next_available_merge_root(output_dir, merge_name)


def merge_sources(
    source_paths: list[Path],
    output_dir: Path,
    output_formats: list[str],
    *,
    target_name: str | None = None,
    enhancer: str | None = None,
    enhance_scale: float = 1.5,
    strategy: str = "quality_auto",
    waifu2x_noise: int = 0,
    waifu2x_tta: bool = False,
    waifu2x_model: str = "models-cunet",
    image_format: str = "jpg",
    quality_mode: str = "fast_auto",
    keep_original_pages: bool = True,
    keep_enhanced_pages: bool = True,
    progress_callback: Callable[[int, str], None] | None = None,
) -> dict[str, object]:
    if len(source_paths) < 2:
        raise ValueError("Select at least two source files or folders to merge.")

    tools = discover_tools()
    output_dir.mkdir(parents=True, exist_ok=True)
    requested_name = target_name or _merge_name(source_paths)
    merge_name, merge_root = _resolve_merge_root(output_dir, requested_name)
    pages_dir = merge_root / "pages_merged"
    reset_dir(pages_dir)

    logs: list[str] = []
    page_index = 1

    with tempfile.TemporaryDirectory(prefix="manga_merge_") as temp_dir:
        temp_root = Path(temp_dir)
        for source_order, source_path in enumerate(source_paths, start=1):
            logs.append(f"merge source {source_order}: {source_path}")
            if progress_callback:
                progress = min(28, 8 + int((source_order / max(len(source_paths), 1)) * 20))
                progress_callback(progress, f"Merging source {source_order}/{len(source_paths)}")
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
    export_source_dir = pages_dir
    enhancement_summary: dict[str, object] = {}

    if enhancer not in {None, "", "auto"}:
        logs.append(f"merge enhance: enhancer={enhancer} scale={enhance_scale} strategy={strategy}")
        enhanced_dir = merge_root / "pages_ai"
        if progress_callback:
            progress_callback(32, "Enhancing merged pages")
        enhance_result = enhance_pages(
            pages_dir=pages_dir,
            enhanced_dir=enhanced_dir,
            options=EnhanceOptions(
                mode="standard",
                scale=enhance_scale or 1.5,
                noise=waifu2x_noise,
                tta=waifu2x_tta,
                model=waifu2x_model or "models-cunet",
            ),
            enhancer_name=enhancer,
            strategy=strategy or "quality_auto",
            output_format=image_format,
            quality_mode=quality_mode,
            progress_callback=lambda total, processed, filename: (
                progress_callback(
                    min(88, 32 + int((processed / max(total, 1)) * 56)),
                    f"Enhancing merged pages {processed}/{total}: {filename}",
                )
                if progress_callback
                else None
            ),
        )
        export_source_dir = enhanced_dir
        enhancement_summary = {
            "enhanced": True,
            "enhancer": enhancer,
            "success_count": enhance_result.success_count,
            "skipped_count": enhance_result.skipped_count,
            "total_count": enhance_result.total_count,
            "profile_counts": enhance_result.profile_counts,
            "model_availability": enhance_result.model_availability,
        }
        logs.extend(f"[merge-enhance-warning] {item}" for item in enhance_result.warnings[:20])
    else:
        logs.append("merge enhance: skipped (no enhancer selected)")

    exported_files: list[str] = []

    if "cbz" in selected_formats:
        if progress_callback:
            progress_callback(92, "Packaging CBZ")
        exported_files.append(str(export_cbz(export_source_dir, merge_root / f"{merge_name}.cbz")))
    if "zip" in selected_formats:
        if progress_callback:
            progress_callback(92, "Packaging ZIP")
        exported_files.append(str(export_zip(export_source_dir, merge_root / f"{merge_name}.zip")))
    if "pdf" in selected_formats:
        if progress_callback:
            progress_callback(92, "Packaging PDF")
        exported_files.append(str(export_pdf(export_source_dir, merge_root / f"{merge_name}.pdf")))

    if {"epub", "mobi"} & selected_formats:
        if not tools.kcc.available:
            raise RuntimeError("KCC is required for EPUB or MOBI merge export.")
        extra_args: list[str] = []
        if "mobi" in selected_formats and "epub" not in selected_formats:
            extra_args = ["--mobi"]
        run_kcc(tools.kcc, export_source_dir, merge_root, extra_args=extra_args)
        if "epub" in selected_formats:
            exported_files.extend(str(path) for path in merge_root.glob("*.epub"))
        if "mobi" in selected_formats:
            exported_files.extend(str(path) for path in merge_root.glob("*.mobi"))

    kept_paths: list[str] = []
    removed_paths: list[str] = []
    if pages_dir.exists():
        if keep_original_pages:
            kept_paths.append(str(pages_dir))
        else:
            shutil.rmtree(pages_dir, ignore_errors=True)
            removed_paths.append(str(pages_dir))
    enhanced_dir = merge_root / "pages_ai"
    if enhanced_dir.exists():
        if keep_enhanced_pages:
            kept_paths.append(str(enhanced_dir))
        else:
            shutil.rmtree(enhanced_dir, ignore_errors=True)
            removed_paths.append(str(enhanced_dir))

    manifest = {
        "merge_name": merge_name,
        "sources": [str(path) for path in source_paths],
        "page_count": page_index - 1,
        "output_dir": str(merge_root),
        "output_formats": sorted(selected_formats),
        "files": [*exported_files, *kept_paths],
        "output_files": exported_files,
        "logs": logs,
        "enhancement": enhancement_summary,
        "kept_paths": kept_paths,
        "removed_paths": removed_paths,
    }
    manifest_path = merge_root / "merge_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest"] = str(manifest_path)
    if progress_callback:
        progress_callback(98, "Writing merge manifest")
    return manifest
