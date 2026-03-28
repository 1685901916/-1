from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import fitz

from .tools import CommandSpec
from .utils import iter_image_files


def export_cbz(source_dir: Path, target_file: Path) -> Path:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    base = target_file.with_suffix("")
    archive = shutil.make_archive(str(base), "zip", root_dir=source_dir)
    archive_path = Path(archive)
    final_path = target_file.with_suffix(".cbz")
    if archive_path == final_path:
        return final_path
    if final_path.exists():
        final_path.unlink()
    archive_path.replace(final_path)
    return final_path


def export_zip(source_dir: Path, target_file: Path) -> Path:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    base = target_file.with_suffix("")
    archive = shutil.make_archive(str(base), "zip", root_dir=source_dir)
    archive_path = Path(archive)
    final_path = target_file.with_suffix(".zip")
    if archive_path == final_path:
        return final_path
    if final_path.exists():
        final_path.unlink()
    archive_path.replace(final_path)
    return final_path


def export_pdf(source_dir: Path, target_file: Path) -> Path:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    final_path = target_file.with_suffix(".pdf")
    images = list(iter_image_files(source_dir))
    if not images:
        raise RuntimeError(f"No images found for PDF export: {source_dir}")

    document = fitz.open()
    try:
        for image_path in images:
            pixmap = fitz.Pixmap(str(image_path))
            try:
                page = document.new_page(width=pixmap.width, height=pixmap.height)
                page.insert_image(page.rect, filename=str(image_path))
            finally:
                del pixmap
        document.save(final_path)
    finally:
        document.close()
    return final_path


def run_kcc(kcc: CommandSpec, source_dir: Path, output_dir: Path, extra_args: list[str] | None = None) -> Path:
    if not kcc.available:
        raise RuntimeError("KCC is not available. Install it or set KCC_CMD to the executable path.")

    output_dir.mkdir(parents=True, exist_ok=True)
    command = [*kcc.command, str(source_dir), "-o", str(output_dir)]
    if extra_args:
        command.extend(extra_args)

    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "KCC failed with exit code "
            f"{completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return output_dir
