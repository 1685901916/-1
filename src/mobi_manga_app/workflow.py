from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .analyze import analyze_pages
from .config import Workspace
from .enhance import EnhanceOptions, enhance_pages
from .job_store import StoredJob
from .repack import export_cbz, export_pdf, export_zip, run_kcc
from .tools import discover_tools
from .unpack import PdfUnpackOptions, unpack_and_collect
from .utils import iter_image_files


def _next_available_output_root(output_dir: Path, source_stem: str) -> Path:
    candidate = output_dir / source_stem
    suffix = 1
    while candidate.exists():
        candidate = output_dir / f"{source_stem}({suffix})"
        suffix += 1
    return candidate


def _is_concrete_output_root(path: Path, source_stem: str) -> bool:
    return bool(re.fullmatch(rf"{re.escape(source_stem)}(?:\(\d+\))?", path.name))


def _book_output_root(job: StoredJob) -> Path:
    source_stem = Path(job.source_name).stem or Path(job.name).stem or "job"
    output_dir = Path(job.output_dir)
    if _is_concrete_output_root(output_dir, source_stem):
        return output_dir
    resolved_root = _next_available_output_root(output_dir, source_stem)
    job.output_dir = str(resolved_root)
    return resolved_root


def _copy_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source, target)


def _write_manifest(target_root: Path, payload: dict) -> Path:
    manifest_path = target_root / "manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def _ensure_pages_exist(workspace: Workspace) -> None:
    if not workspace.pages_dir.exists() or not any(workspace.pages_dir.iterdir()):
        raise FileNotFoundError("Missing pages directory. Run import first.")


def _ensure_pages_ai_exist(workspace: Workspace) -> None:
    if not workspace.enhanced_dir.exists() or not any(workspace.enhanced_dir.iterdir()):
        raise FileNotFoundError("Missing pages_ai directory. Run enhance first.")


def _is_image_folder(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        next(iter_image_files(path))
        return True
    except StopIteration:
        return False


def _materialize_pages(job: StoredJob, workspace: Workspace, output_root: Path) -> Path:
    if workspace.pages_dir.exists() and any(workspace.pages_dir.iterdir()):
        return workspace.pages_dir

    source_path = Path(job.source_path)
    if _is_image_folder(source_path):
        _copy_tree(source_path, workspace.pages_dir)
        return workspace.pages_dir

    exported_pages = output_root / "pages"
    if exported_pages.exists() and any(exported_pages.iterdir()):
        _copy_tree(exported_pages, workspace.pages_dir)
        return workspace.pages_dir

    if source_path.is_file():
        tools = discover_tools()
        unpack_and_collect(
            source_path,
            workspace.unpacked_dir,
            workspace.pages_dir,
            tools.kindleunpack,
            PdfUnpackOptions(
                mode=job.pdf_mode,
                quality_mode=job.pdf_quality_mode,
                image_format=job.pdf_image_format,
                render_dpi=job.pdf_render_dpi,
            ),
        )
        return workspace.pages_dir

    raise FileNotFoundError("Missing available pages directory.")


def _materialize_enhanced(job: StoredJob, workspace: Workspace, output_root: Path) -> Path:
    if workspace.optimized_dir.exists() and any(workspace.optimized_dir.iterdir()):
        return workspace.optimized_dir
    if workspace.enhanced_dir.exists() and any(workspace.enhanced_dir.iterdir()):
        return workspace.enhanced_dir

    source_path = Path(job.source_path)
    if _is_image_folder(source_path):
        _copy_tree(source_path, workspace.enhanced_dir)
        return workspace.enhanced_dir

    exported_pages_ai = output_root / "pages_ai"
    if exported_pages_ai.exists() and any(exported_pages_ai.iterdir()):
        _copy_tree(exported_pages_ai, workspace.enhanced_dir)
        return workspace.enhanced_dir

    exported_pages = output_root / "pages"
    if exported_pages.exists() and any(exported_pages.iterdir()):
        _copy_tree(exported_pages, workspace.enhanced_dir)
        return workspace.enhanced_dir

    pages_dir = _materialize_pages(job, workspace, output_root)
    if pages_dir.exists() and any(pages_dir.iterdir()):
        _copy_tree(pages_dir, workspace.enhanced_dir)
        return workspace.enhanced_dir

    raise FileNotFoundError("Missing available enhanced pages directory.")


def _collect_export_files(output_root: Path, source_stem: str, selected_formats: set[str]) -> list[str]:
    files: list[str] = []
    if "cbz" in selected_formats:
        files.append(str(output_root / f"{source_stem}.cbz"))
    if "zip" in selected_formats:
        files.append(str(output_root / f"{source_stem}.zip"))
    if "pdf" in selected_formats:
        files.append(str(output_root / f"{source_stem}.pdf"))
    if "epub" in selected_formats:
        files.extend(str(path) for path in output_root.glob("*.epub"))
    if "mobi" in selected_formats:
        files.extend(str(path) for path in output_root.glob("*.mobi"))
    return [path for path in files if Path(path).exists()]


def summarize_job_context(job: StoredJob) -> list[str]:
    return [
        f"source: {job.source_path}",
        f"workspace: {job.workspace}",
        f"output_dir: {job.output_dir}",
        f"formats: {', '.join(job.output_formats or ['cbz'])}",
        f"strategy: {job.strategy or 'quality_auto'}",
        f"enhancer: {job.enhancer or 'auto'}",
        f"keep_original_pages: {job.keep_original_pages}",
        f"keep_enhanced_pages: {job.keep_enhanced_pages}",
        f"pdf_mode: {job.pdf_mode}",
        f"pdf_quality_mode: {job.pdf_quality_mode}",
        f"pdf_image_format: {job.pdf_image_format}",
        f"pdf_render_dpi: {job.pdf_render_dpi}",
    ]


def _prune_output_images(job: StoredJob, output_root: Path) -> list[str]:
    removed: list[str] = []
    pages_dir = output_root / "pages"
    pages_ai_dir = output_root / "pages_ai"

    if not job.keep_original_pages and pages_dir.exists():
        shutil.rmtree(pages_dir, ignore_errors=True)
        removed.append(str(pages_dir))

    if not job.keep_enhanced_pages and pages_ai_dir.exists():
        shutil.rmtree(pages_ai_dir, ignore_errors=True)
        removed.append(str(pages_ai_dir))

    if removed:
        job.outputs = [path for path in job.outputs if path not in removed]
    return removed


def run_import_only(job: StoredJob) -> StoredJob:
    workspace = Workspace(Path(job.workspace))
    workspace.root.mkdir(parents=True, exist_ok=True)

    source_path = Path(job.source_path)
    tools = discover_tools()
    if not tools.kindleunpack.available and source_path.suffix.lower() not in {".cbz", ".zip"} and not source_path.is_dir():
        raise RuntimeError(
            "KindleUnpack unavailable. Expected bundled script or KINDLEUNPACK_CMD. "
            f"tool_source={tools.kindleunpack.source}"
        )

    job.status = "running"
    job.stage = "import"
    unpack_result = unpack_and_collect(
        source_path,
        workspace.unpacked_dir,
        workspace.pages_dir,
        tools.kindleunpack,
        PdfUnpackOptions(
            mode=job.pdf_mode,
            quality_mode=job.pdf_quality_mode,
            image_format=job.pdf_image_format,
            render_dpi=job.pdf_render_dpi,
        ),
    )
    job.page_count = unpack_result.page_count

    output_root = _book_output_root(job)
    output_root.mkdir(parents=True, exist_ok=True)
    export_pages_dir = output_root / "pages"
    _copy_tree(workspace.pages_dir, export_pages_dir)

    manifest_path = _write_manifest(
        output_root,
        {
            "source_file": job.source_path,
            "source_name": job.source_name,
            "stage": "import",
            "page_count": unpack_result.page_count,
            "files": [str(export_pages_dir)],
        },
    )

    job.outputs = [str(export_pages_dir), str(manifest_path)]
    job.notes = [f"pages: {unpack_result.page_count}", f"output_dir: {output_root}", "import complete"]
    job.status = "ready"
    return job


def run_analyze_only(job: StoredJob) -> StoredJob:
    workspace = Workspace(Path(job.workspace))
    _ensure_pages_exist(workspace)

    job.status = "running"
    job.stage = "analyze"

    pdf_split_meta = None
    if workspace.pdf_split_meta_file.exists():
        pdf_split_meta = json.loads(workspace.pdf_split_meta_file.read_text(encoding="utf-8"))
    analysis = analyze_pages(workspace.pages_dir, pdf_split_meta=pdf_split_meta)
    summary = analysis.get("summary", {})
    workspace.analysis_file.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

    output_root = _book_output_root(job)
    output_root.mkdir(parents=True, exist_ok=True)
    export_pages_dir = output_root / "pages"
    if not export_pages_dir.exists():
        _copy_tree(workspace.pages_dir, export_pages_dir)

    exported_analysis = output_root / "analysis.json"
    exported_analysis.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path = _write_manifest(
        output_root,
        {
            "source_file": job.source_path,
            "source_name": job.source_name,
            "stage": "analyze",
            "page_count": summary.get("page_count"),
            "files": [str(export_pages_dir), str(exported_analysis)],
        },
    )

    if summary.get("page_count"):
        job.page_count = summary["page_count"]
    outputs = set(job.outputs)
    outputs.update({str(export_pages_dir), str(exported_analysis), str(manifest_path)})
    job.outputs = sorted(outputs)
    job.notes = [f"pages: {job.page_count or '-'}", f"output_dir: {output_root}", "analysis complete"]
    if pdf_split_meta:
        summary = pdf_split_meta.get("summary") or {}
        job.notes.append(
            f"pdf split: extract={summary.get('extract_pages', 0)} render={summary.get('render_pages', 0)}"
        )
    job.status = "ready"
    return job


def run_enhance_only(job: StoredJob) -> StoredJob:
    workspace = Workspace(Path(job.workspace))
    output_root = _book_output_root(job)
    _materialize_pages(job, workspace, output_root)

    job.status = "running"
    job.stage = "enhance"
    enhancer_name = job.enhancer or None
    analysis = None
    if workspace.analysis_file.exists():
        try:
            analysis = json.loads(workspace.analysis_file.read_text(encoding="utf-8"))
        except Exception:
            analysis = None

    enhance_result = enhance_pages(
        pages_dir=workspace.pages_dir,
        enhanced_dir=workspace.enhanced_dir,
        options=EnhanceOptions(
            mode="standard",
            scale=job.enhance_scale or 1.5,
            noise=job.waifu2x_noise,
            tta=job.waifu2x_tta,
            model=job.waifu2x_model or "models-cunet",
        ),
        enhancer_name=enhancer_name,
        strategy=job.strategy or "quality_auto",
        analysis=analysis,
        output_format=job.pdf_image_format or "jpg",
        quality_mode=job.pdf_quality_mode or "fast_auto",
    )

    output_root.mkdir(parents=True, exist_ok=True)
    pages_ai_dir = output_root / "pages_ai"
    _copy_tree(workspace.enhanced_dir, pages_ai_dir)
    if not (output_root / "pages").exists() and workspace.pages_dir.exists():
        _copy_tree(workspace.pages_dir, output_root / "pages")

    outputs = set(job.outputs)
    outputs.update({str(output_root / "pages"), str(pages_ai_dir)})
    job.outputs = sorted(outputs)
    job.enhancement_profile_counts = enhance_result.profile_counts
    job.page_enhancements = enhance_result.page_results
    job.model_availability = enhance_result.model_availability
    fallback_only = bool(enhance_result.total_count) and enhance_result.success_count == 0 and enhance_result.skipped_count == enhance_result.total_count
    job.notes = [
        f"pages_ai success: {enhance_result.success_count}/{enhance_result.total_count}",
        f"pages_ai fallback: {enhance_result.skipped_count}",
        f"strategy: {job.strategy or 'quality_auto'}",
        f"pdf_quality_mode: {job.pdf_quality_mode}",
        f"output_dir: {output_root}",
        "enhancement complete" if not fallback_only else "enhancement fallback only",
    ]
    if enhance_result.warnings:
        job.logs.extend(f"[enhance-warning] {item}" for item in enhance_result.warnings[:20])
    if fallback_only:
        job.logs.append("[enhance-warning] all pages fell back to the original images")
        job.progress_label = "Enhancement complete (fallback only)"
    job.status = "ready"
    return job


def run_optimize_only(job: StoredJob) -> StoredJob:
    workspace = Workspace(Path(job.workspace))
    output_root = _book_output_root(job)
    _materialize_enhanced(job, workspace, output_root)

    job.status = "running"
    job.stage = "optimize"
    _copy_tree(workspace.enhanced_dir, workspace.optimized_dir)

    output_root.mkdir(parents=True, exist_ok=True)
    pages_ai_dir = output_root / "pages_ai"
    _copy_tree(workspace.optimized_dir, pages_ai_dir)

    outputs = set(job.outputs)
    outputs.update({str(output_root / "pages"), str(pages_ai_dir)})
    job.outputs = sorted(outputs)
    job.notes = [f"pages_ai optimized: {len(list(workspace.optimized_dir.iterdir()))}", f"output_dir: {output_root}", "optimization complete"]
    job.status = "ready"
    return job


def run_package_only(job: StoredJob) -> StoredJob:
    workspace = Workspace(Path(job.workspace))
    output_root = _book_output_root(job)
    source_dir = _materialize_enhanced(job, workspace, output_root)

    job.status = "running"
    job.stage = "package"

    output_root.mkdir(parents=True, exist_ok=True)
    selected_formats = set(job.output_formats or ["cbz"])
    source_stem = Path(job.source_name).stem
    exported_files: list[str] = []

    if "cbz" in selected_formats:
        exported_files.append(str(export_cbz(source_dir, output_root / f"{source_stem}.cbz")))
    if "zip" in selected_formats:
        exported_files.append(str(export_zip(source_dir, output_root / f"{source_stem}.zip")))
    if "pdf" in selected_formats:
        exported_files.append(str(export_pdf(source_dir, output_root / f"{source_stem}.pdf")))

    tools = discover_tools()
    if {"epub", "mobi"} & selected_formats:
        if not tools.kcc.available:
            raise RuntimeError("KCC is required for EPUB or MOBI export.")
        extra_args: list[str] = []
        if "mobi" in selected_formats and "epub" not in selected_formats:
            extra_args = ["--mobi"]
        run_kcc(tools.kcc, source_dir, output_root, extra_args=extra_args)
        exported_files = _collect_export_files(output_root, source_stem, selected_formats)

    outputs = set(job.outputs)
    outputs.update(exported_files)
    job.outputs = sorted(outputs)
    job.notes = [f"output_dir: {output_root}", "packaging complete"]
    job.status = "ready"
    return job


def run_export_only(job: StoredJob, *, cleanup_intermediate: bool = False) -> StoredJob:
    workspace = Workspace(Path(job.workspace))
    output_root = _book_output_root(job)
    output_root.mkdir(parents=True, exist_ok=True)

    files = _collect_export_files(output_root, Path(job.source_name).stem, set(job.output_formats or ["cbz"]))
    if not files:
        raise FileNotFoundError("No packaged output found. Run package first.")

    manifest = {
        "source_file": job.source_path,
        "source_name": job.source_name,
        "page_count": job.page_count,
        "output_dir": str(output_root),
        "output_formats": sorted(set(job.output_formats or ["cbz"])),
        "strategy": job.strategy or "quality_auto",
        "enhancer": job.enhancer or "auto",
        "pdf_mode": job.pdf_mode,
        "pdf_quality_mode": job.pdf_quality_mode,
        "pdf_render_dpi": job.pdf_render_dpi,
        "keep_original_pages": job.keep_original_pages,
        "keep_enhanced_pages": job.keep_enhanced_pages,
        "enhancement_profile_counts": job.enhancement_profile_counts,
        "page_enhancements": job.page_enhancements,
        "model_availability": job.model_availability,
        "pdf_summary": {},
        "files": files,
    }
    if workspace.pdf_split_meta_file.exists():
        try:
            pdf_split_meta = json.loads(workspace.pdf_split_meta_file.read_text(encoding="utf-8"))
            manifest["pdf_summary"] = dict(pdf_split_meta.get("summary") or {})
        except Exception:
            pass
    manifest_path = _write_manifest(output_root, manifest)
    files.append(str(manifest_path))

    removed = _prune_output_images(job, output_root)

    if cleanup_intermediate:
        for path in (workspace.unpacked_dir, workspace.pages_dir, workspace.enhanced_dir, workspace.optimized_dir):
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
        if workspace.analysis_file.exists():
            workspace.analysis_file.unlink()

    job.stage = "export"
    job.status = "ready"
    job.outputs = sorted(set(job.outputs).union(files))
    if removed:
        job.notes = [f"output_dir: {output_root}", f"removed: {', '.join(removed)}", "manifest complete"]
    else:
        job.notes = [f"output_dir: {output_root}", "manifest complete"]
    return job


def run_export_module(job: StoredJob) -> StoredJob:
    job = run_package_only(job)
    return run_export_only(job, cleanup_intermediate=False)


def run_import_analyze(job: StoredJob) -> StoredJob:
    job = run_import_only(job)
    return run_analyze_only(job)


def run_full_pipeline(
    job: StoredJob,
    *,
    progress_callback: callable | None = None,
    cleanup_intermediate: bool = True,
) -> StoredJob:
    def report(progress: int, stage: str, label: str) -> None:
        if progress_callback:
            progress_callback(progress, stage, label)

    report(8, "import", "Importing pages")
    job = run_import_only(job)

    report(24, "analyze", "Analyzing pages")
    job = run_analyze_only(job)

    report(48, "enhance", "Enhancing pages")
    job = run_enhance_only(job)

    report(68, "optimize", "Preparing pages_ai")
    job = run_optimize_only(job)

    report(84, "package", "Packaging outputs")
    job = run_package_only(job)

    report(96, "export", "Writing manifest")
    job = run_export_only(job, cleanup_intermediate=cleanup_intermediate)

    report(100, "export", "Completed")
    return job
