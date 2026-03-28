from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .analyze import analyze_pages
from .config import Workspace
from .enhance import EnhanceOptions, enhance_pages
from .repack import export_cbz, run_kcc
from .tools import discover_tools
from .unpack import PdfUnpackOptions, unpack_and_collect
from .utils import path_size_mb, write_json


@dataclass(slots=True)
class ProcessOptions:
    input_path: Path
    workspace_root: Path
    strategy: str
    mode: str
    scale: float
    skip_kcc: bool
    kcc_args: list[str]
    model: str | None = None
    pdf_mode: str = "auto"
    pdf_quality_mode: str = "fast_auto"
    pdf_image_format: str = "jpg"
    pdf_render_dpi: int = 300


def process_mobi(options: ProcessOptions) -> dict[str, object]:
    tools = discover_tools()
    workspace = Workspace(options.workspace_root)
    workspace.ensure()

    unpack_result = unpack_and_collect(
        input_path=options.input_path,
        unpack_dir=workspace.unpacked_dir,
        pages_dir=workspace.pages_dir,
        kindleunpack=tools.kindleunpack,
        pdf_options=PdfUnpackOptions(
            mode=options.pdf_mode,
            quality_mode=options.pdf_quality_mode,
            image_format=options.pdf_image_format,
            render_dpi=options.pdf_render_dpi,
        ),
    )

    pdf_split_meta = None
    if workspace.pdf_split_meta_file.exists():
        pdf_split_meta = json.loads(workspace.pdf_split_meta_file.read_text(encoding="utf-8"))
    analysis = analyze_pages(workspace.pages_dir, pdf_split_meta=pdf_split_meta)
    write_json(workspace.analysis_file, analysis)

    enhance_count = enhance_pages(
        pages_dir=workspace.pages_dir,
        enhanced_dir=workspace.enhanced_dir,
        options=EnhanceOptions(mode=options.mode, scale=options.scale),
        enhancer_name=options.model,
        strategy=options.strategy,
        analysis=analysis,
    )

    cbz_path = export_cbz(workspace.enhanced_dir, workspace.export_dir / f"{options.input_path.stem}_enhanced.cbz")

    kcc_output = None
    if not options.skip_kcc and tools.kcc.available:
        run_kcc(tools.kcc, workspace.enhanced_dir, workspace.export_dir, extra_args=options.kcc_args)
        kcc_output = str(workspace.export_dir)

    manifest = {
        "input_file": str(options.input_path),
        "input_size_mb": round(path_size_mb(options.input_path), 2),
        "workspace": str(workspace.root),
        "unpacked_page_count": unpack_result.page_count,
        "enhanced_page_count": enhance_count.success_count,
        "analysis_file": str(workspace.analysis_file),
        "enhanced_cbz": str(cbz_path),
        "kcc_output": kcc_output,
        "tools": {
            "kindleunpack": asdict(tools.kindleunpack),
            "kcc": asdict(tools.kcc),
        },
        "enhance_options": {"mode": options.mode, "scale": options.scale, "strategy": options.strategy},
        "pdf_options": {
            "mode": options.pdf_mode,
            "quality_mode": options.pdf_quality_mode,
            "image_format": options.pdf_image_format,
            "render_dpi": options.pdf_render_dpi,
        },
        "pdf_summary": analysis.get("summary", {}),
        "enhancement_summary": {
            "success_count": enhance_count.success_count,
            "fallback_count": enhance_count.skipped_count,
            "profile_counts": enhance_count.profile_counts,
            "model_availability": enhance_count.model_availability,
        },
    }
    write_json(workspace.manifest_file, manifest)
    return manifest
