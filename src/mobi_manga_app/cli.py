from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analyze import analyze_pages
from .config import Workspace
from .enhance import EnhanceOptions, enhance_pages
from .enhancers import list_enhancers
from .pipeline import ProcessOptions, process_mobi
from .tools import discover_tools
from .unpack import unpack_and_collect
from .utils import write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MOBI manga enhancement pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Show available external tools")

    subparsers.add_parser("list-models", help="List available enhancement models")

    unpack_parser = subparsers.add_parser("unpack", help="Unpack a MOBI file and normalize page images")
    unpack_parser.add_argument("input", type=Path)
    unpack_parser.add_argument("--workspace", type=Path, required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a directory of page images")
    analyze_parser.add_argument("pages", type=Path)
    analyze_parser.add_argument("--output", type=Path)

    enhance_parser = subparsers.add_parser("enhance-pages", help="Enhance a directory of page images")
    enhance_parser.add_argument("pages", type=Path)
    enhance_parser.add_argument("--output", type=Path, required=True)
    enhance_parser.add_argument("--mode", choices=["conservative", "standard", "strong"], default="standard")
    enhance_parser.add_argument("--scale", type=float, default=2.0)
    enhance_parser.add_argument("--strategy", default="quality_auto")
    enhance_parser.add_argument("--model", type=str, help="Enhancement model (opencv, realesrgan, etc.)")

    process_parser = subparsers.add_parser("process", help="Run unpack, analyze, enhance, and export")
    process_parser.add_argument("input", type=Path)
    process_parser.add_argument("--workspace", type=Path, required=True)
    process_parser.add_argument("--mode", choices=["conservative", "standard", "strong"], default="standard")
    process_parser.add_argument("--scale", type=float, default=2.0)
    process_parser.add_argument("--strategy", default="quality_auto")
    process_parser.add_argument("--model", type=str, help="Enhancement model (opencv, realesrgan, etc.)")
    process_parser.add_argument("--pdf-mode", default="auto")
    process_parser.add_argument("--pdf-quality-mode", default="fast_auto")
    process_parser.add_argument("--pdf-image-format", default="jpg")
    process_parser.add_argument("--pdf-render-dpi", type=int, default=300)
    process_parser.add_argument("--skip-kcc", action="store_true")
    process_parser.add_argument("--kcc-arg", action="append", default=[])

    return parser


def _print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=True, indent=2))


def command_doctor() -> int:
    tools = discover_tools()
    payload = {
        "kindleunpack": {"available": tools.kindleunpack.available, "command": tools.kindleunpack.command, "source": tools.kindleunpack.source},
        "kcc": {"available": tools.kcc.available, "command": tools.kcc.command, "source": tools.kcc.source},
    }
    _print_json(payload)
    return 0


def command_list_models() -> int:
    models = list_enhancers()
    _print_json({"models": models})
    return 0


def command_unpack(input_path: Path, workspace_root: Path) -> int:
    workspace = Workspace(workspace_root)
    workspace.ensure()
    tools = discover_tools()
    result = unpack_and_collect(input_path, workspace.unpacked_dir, workspace.pages_dir, tools.kindleunpack)
    payload = {
        "input": str(input_path),
        "unpacked_dir": str(result.unpack_root),
        "pages_dir": str(result.pages_dir),
        "page_count": result.page_count,
    }
    _print_json(payload)
    return 0


def command_analyze(pages_dir: Path, output_file: Path | None) -> int:
    analysis = analyze_pages(pages_dir)
    if output_file:
        write_json(output_file, analysis)
    _print_json(analysis["summary"])
    return 0


def command_enhance_pages(pages_dir: Path, output_dir: Path, mode: str, scale: float, strategy: str, model: str | None) -> int:
    result = enhance_pages(
        pages_dir,
        output_dir,
        EnhanceOptions(mode=mode, scale=scale),
        model,
        strategy=strategy,
    )
    _print_json(
        {
            "pages_enhanced": result.success_count,
            "fallback_count": result.skipped_count,
            "output_dir": str(output_dir),
            "mode": mode,
            "scale": scale,
            "strategy": strategy,
            "model": model or "auto",
            "profile_counts": result.profile_counts,
            "model_availability": result.model_availability,
        }
    )
    return 0


def command_process(args: argparse.Namespace) -> int:
    manifest = process_mobi(
        ProcessOptions(
            input_path=args.input,
            workspace_root=args.workspace,
            strategy=args.strategy,
            mode=args.mode,
            scale=args.scale,
            skip_kcc=args.skip_kcc,
            kcc_args=args.kcc_arg,
            model=args.model,
            pdf_mode=args.pdf_mode,
            pdf_quality_mode=args.pdf_quality_mode,
            pdf_image_format=args.pdf_image_format,
            pdf_render_dpi=args.pdf_render_dpi,
        )
    )
    _print_json(manifest)
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "doctor":
        return command_doctor()
    if args.command == "list-models":
        return command_list_models()
    if args.command == "unpack":
        return command_unpack(args.input, args.workspace)
    if args.command == "analyze":
        return command_analyze(args.pages, args.output)
    if args.command == "enhance-pages":
        return command_enhance_pages(args.pages, args.output, args.mode, args.scale, args.strategy, args.model)
    if args.command == "process":
        return command_process(args)

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
