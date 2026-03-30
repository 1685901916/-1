from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .utils import iter_image_files


@dataclass(slots=True)
class PageMetrics:
    file: str
    width: int
    height: int
    channels: int
    is_color: bool
    megapixels: float
    sharpness: float
    edge_density: float
    blockiness: float
    text_density: float
    line_density: float
    halftone_score: float
    noise_score: float
    background_cleanliness: float
    page_profile: str
    quality_score: float


def _estimate_blockiness(gray: np.ndarray) -> float:
    if gray.shape[0] < 16 or gray.shape[1] < 16:
        return 0.0

    boundary_cols = np.arange(8, gray.shape[1], 8)
    boundary_rows = np.arange(8, gray.shape[0], 8)
    vertical = np.abs(gray[:, boundary_cols] - gray[:, boundary_cols - 1]).mean() if boundary_cols.size else 0.0
    horizontal = np.abs(gray[boundary_rows, :] - gray[boundary_rows - 1, :]).mean() if boundary_rows.size else 0.0
    return float((vertical + horizontal) / 2.0)


def _is_color_image(image: np.ndarray) -> bool:
    if image.ndim < 3 or image.shape[2] < 3:
        return False
    b, g, r = cv2.split(image[:, :, :3])
    channel_delta = np.mean(np.abs(r.astype(np.int16) - g.astype(np.int16))) + np.mean(
        np.abs(g.astype(np.int16) - b.astype(np.int16))
    )
    return bool(channel_delta > 8.0)


def _estimate_text_density(gray: np.ndarray) -> float:
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if num_labels <= 1:
        return 0.0

    total_area = gray.shape[0] * gray.shape[1]
    small_components = 0
    for index in range(1, num_labels):
        _, _, w, h, area = stats[index]
        if area < 6:
            continue
        if w <= max(24, gray.shape[1] * 0.06) and h <= max(24, gray.shape[0] * 0.06):
            small_components += area
    return float(min(1.0, small_components / max(total_area * 0.12, 1)))


def _estimate_line_density(gray: np.ndarray) -> float:
    edges = cv2.Canny(gray, 60, 160)
    return float(np.count_nonzero(edges) / max(edges.size, 1))


def _estimate_halftone_score(gray: np.ndarray) -> float:
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    energy = float(np.mean(np.abs(lap)))
    local = cv2.blur(gray.astype(np.float32), (9, 9))
    residual = float(np.mean(np.abs(gray.astype(np.float32) - local)))
    return float(min(1.0, (energy / 18.0) * 0.45 + (residual / 24.0) * 0.55))


def _estimate_noise_score(gray: np.ndarray) -> float:
    blur = cv2.medianBlur(gray, 3)
    residual = np.abs(gray.astype(np.float32) - blur.astype(np.float32))
    return float(min(1.0, residual.mean() / 24.0))


def _estimate_background_cleanliness(gray: np.ndarray) -> float:
    bright = gray[gray > 200]
    if bright.size == 0:
        return 0.0
    mean = float(bright.mean())
    spread = float(bright.std())
    score = ((mean - 200.0) / 55.0) - (spread / 40.0)
    return float(max(0.0, min(1.0, score)))


def _classify_page_profile(
    *,
    is_color: bool,
    text_density: float,
    line_density: float,
    halftone_score: float,
    noise_score: float,
    background_cleanliness: float,
    blockiness: float,
) -> str:
    if is_color:
        return "color_illustration"
    if noise_score >= 0.42 or blockiness >= 14 or background_cleanliness < 0.18:
        return "low_quality_scan"
    if text_density >= 0.22:
        return "text_heavy"
    if halftone_score >= 0.34:
        return "halftone_gray"
    if line_density >= 0.055:
        return "lineart_bw"
    return "lineart_bw"


def analyze_page(path: Path) -> PageMetrics:
    with Image.open(path) as pil_image:
        width, height = pil_image.size

    if path.suffix.lower() == ".gif":
        with Image.open(path) as gif_image:
            frame = gif_image.convert("RGB")
            image = cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR)
    else:
        image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise RuntimeError(f"Failed to read image: {path}")

    if image.ndim == 2:
        gray = image
        channels = 1
    else:
        channels = image.shape[2]
        gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)

    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    edges = cv2.Canny(gray, 80, 180)
    edge_density = float(np.count_nonzero(edges) / edges.size)
    blockiness = _estimate_blockiness(gray.astype(np.float32))
    megapixels = float((width * height) / 1_000_000.0)
    is_color = bool(_is_color_image(image))
    text_density = _estimate_text_density(gray)
    line_density = _estimate_line_density(gray)
    halftone_score = _estimate_halftone_score(gray)
    noise_score = _estimate_noise_score(gray)
    background_cleanliness = _estimate_background_cleanliness(gray)
    page_profile = _classify_page_profile(
        is_color=is_color,
        text_density=text_density,
        line_density=line_density,
        halftone_score=halftone_score,
        noise_score=noise_score,
        background_cleanliness=background_cleanliness,
        blockiness=blockiness,
    )

    score = 100.0
    score += min(laplacian_var / 20.0, 20.0)
    score += min(megapixels * 4.0, 20.0)
    score -= min(blockiness * 1.2, 30.0)
    score -= min(noise_score * 18.0, 12.0)
    score += min(background_cleanliness * 8.0, 8.0)
    score = max(0.0, min(100.0, score))

    return PageMetrics(
        file=path.name,
        width=width,
        height=height,
        channels=channels,
        is_color=is_color,
        megapixels=round(megapixels, 3),
        sharpness=round(laplacian_var, 3),
        edge_density=round(edge_density, 4),
        blockiness=round(blockiness, 3),
        text_density=round(text_density, 4),
        line_density=round(line_density, 4),
        halftone_score=round(halftone_score, 4),
        noise_score=round(noise_score, 4),
        background_cleanliness=round(background_cleanliness, 4),
        page_profile=page_profile,
        quality_score=round(score, 2),
    )


def analyze_pages(pages_dir: Path, pdf_split_meta: dict[str, object] | None = None) -> dict[str, object]:
    metrics = [analyze_page(path) for path in iter_image_files(pages_dir)]
    if not metrics:
        raise RuntimeError(f"No page images found in {pages_dir}")

    pdf_page_map = {}
    pdf_summary = {}
    if pdf_split_meta:
        pdf_page_map = {
            str(item.get("file")): item
            for item in list(pdf_split_meta.get("pages") or [])
            if isinstance(item, dict) and item.get("file")
        }
        pdf_summary = dict(pdf_split_meta.get("summary") or {})

    summary = {
        "page_count": len(metrics),
        "color_pages": sum(1 for item in metrics if item.is_color),
        "avg_score": round(sum(item.quality_score for item in metrics) / len(metrics), 2),
        "avg_sharpness": round(sum(item.sharpness for item in metrics) / len(metrics), 2),
        "avg_blockiness": round(sum(item.blockiness for item in metrics) / len(metrics), 2),
        "avg_text_density": round(sum(item.text_density for item in metrics) / len(metrics), 4),
        "avg_line_density": round(sum(item.line_density for item in metrics) / len(metrics), 4),
        "avg_halftone_score": round(sum(item.halftone_score for item in metrics) / len(metrics), 4),
        "avg_noise_score": round(sum(item.noise_score for item in metrics) / len(metrics), 4),
        "avg_background_cleanliness": round(sum(item.background_cleanliness for item in metrics) / len(metrics), 4),
        "min_width": min(item.width for item in metrics),
        "max_width": max(item.width for item in metrics),
        "min_height": min(item.height for item in metrics),
        "max_height": max(item.height for item in metrics),
        "profile_counts": {
            profile: sum(1 for item in metrics if item.page_profile == profile)
            for profile in ["lineart_bw", "halftone_gray", "text_heavy", "color_illustration", "low_quality_scan"]
        },
        "pdf_extract_pages": int(pdf_summary.get("extract_pages") or 0),
        "pdf_render_pages": int(pdf_summary.get("render_pages") or 0),
        "pdf_forced_render_pages": int(pdf_summary.get("forced_render_pages") or 0),
    }
    pages = []
    for item in metrics:
        payload = asdict(item)
        payload.update(pdf_page_map.get(item.file, {}))
        pages.append(payload)
    return {"summary": summary, "pages": pages}
