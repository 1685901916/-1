from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import importlib.util
import io
import sys
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

import fitz
import numpy as np
from PIL import Image

from .tools import CommandSpec
from .utils import iter_image_files, reset_dir


@dataclass(slots=True)
class UnpackResult:
    source: Path
    unpack_root: Path
    pages_dir: Path
    page_count: int


@dataclass(slots=True)
class PdfUnpackOptions:
    mode: str = "auto"
    quality_mode: str = "fast_auto"
    image_format: str = "jpg"
    render_dpi: int = 300


@dataclass(slots=True)
class PdfPageDecision:
    page_index: int
    output_name: str
    source_mode: str
    reason: str
    embedded_width: int
    embedded_height: int
    has_vector_content: bool


def _pdf_save_profile(options: PdfUnpackOptions) -> tuple[int, int | None]:
    quality_mode = (options.quality_mode or "fast_auto").lower()
    if quality_mode == "lossless":
        return 100, 6
    if quality_mode == "quality_auto":
        return 93, 5
    return 84, 4

def _ordered_unique(items: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    ordered: list[Path] = []
    for item in items:
        key = item.resolve()
        if key not in seen and item.exists():
            seen.add(key)
            ordered.append(item)
    return ordered


def _extract_referenced_images(text_files: list[Path]) -> list[Path]:
    image_paths: list[Path] = []
    pattern = re.compile(r"""<img\b[^>]*\bsrc=["']([^"']+)["']""", re.IGNORECASE)
    for text_file in text_files:
        content = text_file.read_text(encoding="utf-8", errors="ignore")
        for match in pattern.findall(content):
            candidate = (text_file.parent / match).resolve()
            if candidate.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}:
                image_paths.append(candidate)
    return _ordered_unique(image_paths)


def collect_page_images(unpack_root: Path) -> list[Path]:
    mobi8_text_dir = unpack_root / "mobi8" / "OEBPS" / "Text"
    if mobi8_text_dir.exists():
        text_files = sorted(mobi8_text_dir.glob("*.xhtml"))
        page_images = _extract_referenced_images(text_files)
        if page_images:
            return page_images

    mobi7_book = unpack_root / "mobi7" / "book.html"
    if mobi7_book.exists():
        page_images = _extract_referenced_images([mobi7_book])
        if page_images:
            return page_images

    mobi8_images_dir = unpack_root / "mobi8" / "OEBPS" / "Images"
    if mobi8_images_dir.exists():
        page_images = [path for path in iter_image_files(mobi8_images_dir) if not path.name.lower().startswith("thumb")]
        if page_images:
            return page_images

    mobi7_images_dir = unpack_root / "mobi7" / "Images"
    if mobi7_images_dir.exists():
        page_images = [path for path in iter_image_files(mobi7_images_dir) if not path.name.lower().startswith("thumb")]
        if page_images:
            return page_images

    return list(iter_image_files(unpack_root))


def _ascii_temp_root() -> Path:
    root = Path(tempfile.gettempdir()) / "manga_enhancer_ascii"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run_embedded_script(script_path: str, args: list[str]) -> tuple[int, str, str]:
    module_name = "_manga_enhancer_embedded_cli"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load embedded script: {script_path}")

    module = importlib.util.module_from_spec(spec)
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    original_argv = sys.argv[:]

    try:
        spec.loader.exec_module(module)
        if not hasattr(module, "main"):
            raise RuntimeError(f"Embedded script has no main(): {script_path}")
        sys.argv = [script_path, *args]
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            exit_code = int(module.main())
    finally:
        sys.argv = original_argv

    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()


def unpack_mobi(input_path: Path, output_dir: Path, kindleunpack: CommandSpec) -> Path:
    if not kindleunpack.available:
        raise RuntimeError(
            "KindleUnpack is not available. Install it or set KINDLEUNPACK_CMD to the command or script path."
        )

    reset_dir(output_dir)
    with tempfile.TemporaryDirectory(prefix="ku_", dir=str(_ascii_temp_root())) as temp_dir:
        temp_root = Path(temp_dir)
        safe_input = temp_root / f"source{input_path.suffix.lower()}"
        safe_unpack_root = temp_root / "unpacked"
        shutil.copy2(input_path, safe_input)
        if getattr(sys, "frozen", False) and kindleunpack.script_path:
            returncode, stdout_text, stderr_text = _run_embedded_script(
                kindleunpack.script_path,
                [str(safe_input), str(safe_unpack_root)],
            )
        else:
            command = [*(kindleunpack.command or []), str(safe_input), str(safe_unpack_root)]
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            returncode = completed.returncode
            stdout_text = completed.stdout
            stderr_text = completed.stderr

        if returncode != 0:
            raise RuntimeError(
                "KindleUnpack failed with exit code "
                f"{returncode}\nstdout:\n{stdout_text}\nstderr:\n{stderr_text}"
            )
        shutil.copytree(safe_unpack_root, output_dir, dirs_exist_ok=True)
    return output_dir


def unpack_archive(input_path: Path, output_dir: Path) -> Path:
    reset_dir(output_dir)
    with zipfile.ZipFile(input_path) as archive:
        archive.extractall(output_dir)
    return output_dir


def _pick_pdf_image(document: fitz.Document, image_list: list[tuple]) -> tuple[bytes, str] | None:
    best: tuple[bytes, str] | None = None
    best_area = -1
    for image_info in image_list:
        try:
            xref = image_info[0]
            base_image = document.extract_image(xref)
            width = int(base_image.get("width") or 0)
            height = int(base_image.get("height") or 0)
            area = width * height
            if area <= best_area:
                continue
            image_bytes = base_image.get("image")
            image_ext = str(base_image.get("ext") or "png").lower()
            if not image_bytes:
                continue
            best = (image_bytes, image_ext)
            best_area = area
        except Exception:
            continue
    return best


def _has_vector_content(page: fitz.Page) -> bool:
    try:
        if page.get_text("text").strip():
            return True
    except Exception:
        pass
    try:
        drawings = page.get_drawings()
        if drawings:
            return True
    except Exception:
        pass
    return False


def _target_render_size(page: fitz.Page, options: PdfUnpackOptions) -> tuple[int, int]:
    dpi = max(72, int(options.render_dpi or 300))
    return (
        int(round(float(page.rect.width) * dpi / 72.0)),
        int(round(float(page.rect.height) * dpi / 72.0)),
    )


def _decide_pdf_page_mode(
    document: fitz.Document,
    page: fitz.Page,
    page_index: int,
    image_list: list[tuple],
    options: PdfUnpackOptions,
) -> PdfPageDecision:
    mode = (options.mode or "auto").lower()
    target_width, target_height = _target_render_size(page, options)
    has_vector = _has_vector_content(page)
    picked = _pick_pdf_image(document, image_list)
    embedded_width = 0
    embedded_height = 0

    if picked is not None:
        for image_info in image_list:
            try:
                xref = image_info[0]
                base_image = document.extract_image(xref)
                width = int(base_image.get("width") or 0)
                height = int(base_image.get("height") or 0)
                if width * height > embedded_width * embedded_height:
                    embedded_width = width
                    embedded_height = height
            except Exception:
                continue

    if mode == "extract":
        reason = "forced_extract"
        source_mode = "extract"
    elif mode == "render":
        reason = "forced_render"
        source_mode = "render"
    elif picked is None:
        reason = "no_embedded_image"
        source_mode = "render"
    elif (options.quality_mode or "quality_auto").lower() == "fast_auto":
        reason = "fast_auto_prefer_extract"
        source_mode = "extract"
    elif has_vector:
        reason = "vector_content_detected"
        source_mode = "render"
    elif embedded_width < int(target_width * 0.85) or embedded_height < int(target_height * 0.85):
        reason = "embedded_image_too_small"
        source_mode = "render"
    else:
        reason = "embedded_image_good_enough"
        source_mode = "extract"

    extension = (options.image_format or "png").lower()
    output_name = f"page_{page_index:04d}.{extension}"
    return PdfPageDecision(
        page_index=page_index,
        output_name=output_name,
        source_mode=source_mode,
        reason=reason,
        embedded_width=embedded_width,
        embedded_height=embedded_height,
        has_vector_content=has_vector,
    )


def _render_pdf_page(page: fitz.Page, output_dir: Path, index: int, options: PdfUnpackOptions) -> None:
    dpi = max(72, int(options.render_dpi or 300))
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    image_format = (options.image_format or "png").lower()
    jpeg_quality, webp_method = _pdf_save_profile(options)
    if image_format == "jpg":
        target = output_dir / f"page_{index:04d}.jpg"
        pix.save(target, "jpeg", jpg_quality=jpeg_quality)
        return
    if image_format == "webp":
        target = output_dir / f"page_{index:04d}.webp"
        rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
        Image.fromarray(rgb).save(target, format="WEBP", quality=jpeg_quality, method=webp_method)
        return
    target = output_dir / f"page_{index:04d}.png"
    pix.save(target)


def _write_extracted_pdf_image(image_bytes: bytes, output_dir: Path, index: int, options: PdfUnpackOptions) -> None:
    image_format = (options.image_format or "png").lower()
    jpeg_quality, webp_method = _pdf_save_profile(options)
    suffix = "jpg" if image_format == "jpg" else image_format
    target = output_dir / f"page_{index:04d}.{suffix}"
    with Image.open(io.BytesIO(image_bytes)) as image:
        frame = image.convert("RGB")
        if image_format == "jpg":
            frame.save(target, format="JPEG", quality=jpeg_quality, optimize=jpeg_quality < 100)
            return
        if image_format == "webp":
            frame.save(target, format="WEBP", quality=jpeg_quality, method=webp_method)
            return
        frame.save(target, format="PNG")


def unpack_pdf(input_path: Path, output_dir: Path, options: PdfUnpackOptions | None = None) -> Path:
    reset_dir(output_dir)
    options = options or PdfUnpackOptions()
    document = fitz.open(input_path)
    decisions: list[PdfPageDecision] = []
    try:
        if document.page_count <= 0:
            raise RuntimeError(f"PDF has no pages: {input_path}")
        for index, page in enumerate(document, start=1):
            image_list = page.get_images(full=True)
            decision = _decide_pdf_page_mode(document, page, index, image_list, options)
            decisions.append(decision)
            extracted = _pick_pdf_image(document, image_list) if decision.source_mode == "extract" else None
            if decision.source_mode == "extract" and extracted is not None:
                image_bytes, _image_ext = extracted
                _write_extracted_pdf_image(image_bytes, output_dir, index, options)
                continue
            _render_pdf_page(page, output_dir, index, options)
    finally:
        document.close()
    meta_path = output_dir / "pdf_split_meta.json"
    meta_payload = {
        "summary": {
            "extract_pages": sum(1 for item in decisions if item.source_mode == "extract"),
            "render_pages": sum(1 for item in decisions if item.source_mode == "render"),
            "forced_render_pages": sum(1 for item in decisions if item.reason not in {"forced_render", "no_embedded_image"} and item.source_mode == "render"),
        },
        "pages": [
            {
                "page_index": item.page_index,
                "file": item.output_name,
                "pdf_source_mode": item.source_mode,
                "pdf_render_reason": item.reason,
                "embedded_image_width": item.embedded_width,
                "embedded_image_height": item.embedded_height,
                "pdf_has_vector_content": item.has_vector_content,
            }
            for item in decisions
        ],
    }
    meta_path.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_dir


def normalize_pages(unpack_root: Path, pages_dir: Path) -> int:
    reset_dir(pages_dir)
    page_files = collect_page_images(unpack_root)
    if not page_files:
        raise RuntimeError(f"No images were found under unpack directory: {unpack_root}")

    for index, path in enumerate(page_files, start=1):
        target = pages_dir / f"page_{index:04d}{path.suffix.lower()}"
        shutil.copy2(path, target)

    return len(page_files)


def unpack_and_collect(
    input_path: Path,
    unpack_dir: Path,
    pages_dir: Path,
    kindleunpack: CommandSpec,
    pdf_options: PdfUnpackOptions | None = None,
) -> UnpackResult:
    if input_path.is_dir():
        unpack_root = input_path
    elif input_path.suffix.lower() == ".pdf":
        unpack_root = unpack_pdf(input_path, unpack_dir, pdf_options)
    elif input_path.suffix.lower() in {".cbz", ".zip", ".epub"}:
        unpack_root = unpack_archive(input_path, unpack_dir)
    else:
        unpack_root = unpack_mobi(input_path, unpack_dir, kindleunpack)
    page_count = normalize_pages(unpack_root, pages_dir)
    return UnpackResult(source=input_path, unpack_root=unpack_root, pages_dir=pages_dir, page_count=page_count)
