from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mobi_manga_app.analyze import analyze_pages
from mobi_manga_app.repack import export_cbz
from mobi_manga_app.tools import discover_tools
from mobi_manga_app.unpack import unpack_and_collect


DEFAULT_WAIFU2X = Path(
    r"F:\BaiduNetdiskDownload\VisualNovelUpscaler_v0.2.1\VisualNovelUpscaler\Dependencies\waifu2x-ncnn-vulkan\waifu2x-ncnn-vulkan.exe"
)


def ensure_empty_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def run_waifu2x(input_dir: Path, output_dir: Path, exe_path: Path) -> None:
    ensure_empty_dir(output_dir)
    command = [str(exe_path), "-i", str(input_dir), "-o", str(output_dir), "-n", "1", "-s", "2", "-f", "png"]
    completed = subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError(
            "waifu2x failed\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )


def build_balanced_pages(orig_dir: Path, ai_dir: Path, analysis_file: Path, output_dir: Path) -> dict[str, int]:
    ensure_empty_dir(output_dir)
    analysis = analyze_pages(orig_dir)
    analysis_file.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    analysis_map = {item["file"]: item for item in analysis["pages"]}

    stats = {"ai_pages": 0, "orig_pages": 0}

    for orig_path in sorted(orig_dir.iterdir()):
        if not orig_path.is_file():
            continue
        meta = analysis_map.get(orig_path.name, {})
        width = int(meta.get("width", 0))
        sharpness = float(meta.get("sharpness", 0))
        is_color = bool(meta.get("is_color", False))
        use_ai = width < 1200 or sharpness < 1800 or is_color
        src_path = ai_dir / f"{orig_path.stem}.png" if use_ai else orig_path
        if not src_path.exists():
            src_path = orig_path
            use_ai = False

        if use_ai:
            stats["ai_pages"] += 1
        else:
            stats["orig_pages"] += 1

        with Image.open(src_path) as image:
            image = image.convert("RGB")
            max_w = 1600
            max_h = 2200
            scale = min(max_w / image.width, max_h / image.height, 1.0)
            if scale < 1.0:
                image = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
            output_path = output_dir / f"{orig_path.stem}.jpg"
            image.save(output_path, format="JPEG", quality=90, optimize=True, progressive=False)
    return stats


def process_book(book_path: Path, workspace_root: Path, output_root: Path, waifu2x_exe: Path) -> Path:
    book_name = book_path.stem
    work_dir = workspace_root / book_name
    unpack_dir = work_dir / "unpacked"
    pages_dir = work_dir / "pages"
    ai_dir = work_dir / "pages_ai"
    balanced_dir = work_dir / "pages_balanced"
    analysis_file = work_dir / "analysis.json"
    manifest_file = work_dir / "manifest.json"

    work_dir.mkdir(parents=True, exist_ok=True)
    tools = discover_tools()
    unpack_result = unpack_and_collect(book_path, unpack_dir, pages_dir, tools.kindleunpack)
    run_waifu2x(pages_dir, ai_dir, waifu2x_exe)
    stats = build_balanced_pages(pages_dir, ai_dir, analysis_file, balanced_dir)

    output_root.mkdir(parents=True, exist_ok=True)
    temp_cbz = output_root / f"{book_name}_balanced.cbz"
    result = export_cbz(balanced_dir, temp_cbz)

    manifest = {
        "input": str(book_path),
        "page_count": unpack_result.page_count,
        "ai_pages": stats["ai_pages"],
        "orig_pages": stats["orig_pages"],
        "analysis": str(analysis_file),
        "output": str(result),
    }
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch convert MOBI books to balanced JPG CBZ.")
    parser.add_argument("source_dir", type=Path, help="Directory containing .mobi files.")
    parser.add_argument("--workspace", type=Path, default=REPO_ROOT / ".work" / "batch_balanced")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--waifu2x", type=Path, default=DEFAULT_WAIFU2X)
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of books to process.")
    parser.add_argument("--skip-existing", action="store_true", help="Skip outputs that already exist.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir
    output_dir = args.output or source_dir / "平衡版CBZ"
    workspace = args.workspace

    if not source_dir.exists():
        print(f"Source directory not found: {source_dir}", file=sys.stderr)
        return 2
    if not args.waifu2x.exists():
        print(f"waifu2x executable not found: {args.waifu2x}", file=sys.stderr)
        return 2

    mobi_files = sorted(source_dir.glob("*.mobi"))
    if args.limit > 0:
        mobi_files = mobi_files[: args.limit]

    processed = 0
    for mobi in mobi_files:
        target = output_dir / f"{mobi.stem}_balanced.cbz"
        if args.skip_existing and target.exists():
            print(f"SKIP {mobi.name} -> existing {target.name}")
            continue
        print(f"START {mobi.name}")
        result = process_book(mobi, workspace, output_dir, args.waifu2x)
        print(f"DONE  {result}")
        processed += 1

    print(f"Processed {processed} book(s). Output: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
