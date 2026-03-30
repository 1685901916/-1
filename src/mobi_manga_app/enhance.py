from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image

from .analyze import analyze_page
from .enhancers import EnhanceOptions, get_enhancer
from .enhancers.registry import list_enhancers
from .utils import iter_image_files, reset_dir


@dataclass(slots=True)
class EnhanceAttempt:
    enhancer: str
    options: EnhanceOptions
    reason: str


@dataclass(slots=True)
class EnhanceRunResult:
    success_count: int
    skipped_count: int
    total_count: int
    warnings: list[str] = field(default_factory=list)
    page_results: list[dict[str, object]] = field(default_factory=list)
    profile_counts: dict[str, int] = field(default_factory=dict)
    model_availability: dict[str, bool] = field(default_factory=dict)


def enhance_image(input_path: Path, output_path: Path, options: EnhanceOptions, enhancer_name: str | None = None) -> None:
    image, was_gray = _read_image(input_path)
    enhanced = _run_enhancer(image, options, enhancer_name)
    _write_image(output_path, enhanced, was_gray)


def enhance_pages(
    pages_dir: Path,
    enhanced_dir: Path,
    options: EnhanceOptions,
    enhancer_name: str | None = None,
    *,
    strategy: str = "quality_auto",
    analysis: dict[str, object] | None = None,
    output_format: str | None = None,
    quality_mode: str = "fast_auto",
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> EnhanceRunResult:
    reset_dir(enhanced_dir)
    paths = list(iter_image_files(pages_dir))
    total_count = len(paths)
    if total_count == 0:
        raise RuntimeError("No page images found for enhancement.")
    count = 0
    skipped = 0
    warnings: list[str] = []
    total = 0
    page_results: list[dict[str, object]] = []
    profile_counts: dict[str, int] = {}
    model_availability = {item["name"]: bool(item.get("available")) for item in list_enhancers()}
    if enhancer_name in {"", None, "auto"} and not any(
        model_availability.get(name) for name in ("realesrgan-anime", "waifu2x")
    ):
        raise RuntimeError("No AI enhancer available. Install waifu2x or Real-ESRGAN, or use legacy_compatible strategy.")

    if enhancer_name not in {"", None, "auto"}:
        enhancer = get_enhancer(enhancer_name)
        if not enhancer.is_available():
            raise RuntimeError(f"Requested enhancer unavailable: {enhancer_name}")

    analysis_map = _analysis_lookup(analysis)

    for path in paths:
        total += 1
        target_name = path.name if not output_format else f"{path.stem}.{_normalize_output_suffix(output_format)}"
        target = enhanced_dir / target_name
        page_metrics = analysis_map.get(path.name) or _analysis_entry(analyze_page(path))
        page_profile = str(page_metrics.get("page_profile") or "lineart_bw")
        profile_counts[page_profile] = profile_counts.get(page_profile, 0) + 1
        record = {
            "file": path.name,
            "page_profile": page_profile,
            "strategy": strategy,
            "pdf_source_mode": page_metrics.get("pdf_source_mode"),
            "pdf_render_reason": page_metrics.get("pdf_render_reason"),
            "selected_enhancer": None,
            "fallback": False,
            "fallback_reason": "",
            "attempts": [],
        }

        try:
            image, was_gray = _read_image(path)
            attempts = _build_attempts(
                page_profile=page_profile,
                strategy=strategy,
                requested_enhancer=enhancer_name,
                base_options=options,
                page_metrics=page_metrics,
            )
            output = None
            failure_reason = ""
            for index, attempt in enumerate(attempts):
                record["attempts"].append({"enhancer": attempt.enhancer, "reason": attempt.reason})
                try:
                    candidate = _run_candidate(image, attempt, page_metrics)
                    verdict = _validate_candidate(
                        original=image,
                        candidate=candidate,
                        page_profile=page_profile,
                        page_metrics=page_metrics,
                    )
                    if verdict is not None:
                        failure_reason = verdict
                        continue
                    output = candidate
                    record["selected_enhancer"] = attempt.enhancer
                    if index > 0:
                        record["fallback"] = True
                        record["fallback_reason"] = failure_reason or attempt.reason
                    break
                except Exception as exc:
                    failure_reason = f"{attempt.enhancer}: {exc}"

            if output is None:
                raise RuntimeError(failure_reason or "all enhancement attempts failed")

            _write_image(target, output, was_gray, quality_mode=quality_mode)
            count += 1
        except Exception as exc:
            detail = f"{path.name}: {exc}"
            warnings.append(detail)
            record["fallback"] = True
            record["fallback_reason"] = str(exc)
            _write_passthrough_image(path, target, quality_mode=quality_mode)
            skipped += 1

        page_results.append(record)
        if progress_callback:
            progress_callback(total_count, count + skipped, path.name)
    if count == 0 and skipped == 0:
        raise RuntimeError("Enhancement failed: no page could be processed.\n" + "\n".join(warnings[:8]))
    return EnhanceRunResult(
        success_count=count,
        skipped_count=skipped,
        total_count=total,
        warnings=warnings,
        page_results=page_results,
        profile_counts=profile_counts,
        model_availability=model_availability,
    )


def _analysis_lookup(analysis: dict[str, object] | None) -> dict[str, dict[str, object]]:
    if not analysis:
        return {}
    return {
        str(item.get("file")): item
        for item in list(analysis.get("pages") or [])
        if isinstance(item, dict) and item.get("file")
    }


def _analysis_entry(metrics) -> dict[str, object]:
    return {
        "file": metrics.file,
        "page_profile": metrics.page_profile,
        "text_density": metrics.text_density,
        "line_density": metrics.line_density,
        "halftone_score": metrics.halftone_score,
        "noise_score": metrics.noise_score,
        "background_cleanliness": metrics.background_cleanliness,
        "blockiness": metrics.blockiness,
        "pdf_source_mode": None,
        "pdf_render_reason": None,
        "embedded_image_width": 0,
        "embedded_image_height": 0,
        "pdf_has_vector_content": False,
    }


def _read_image(input_path: Path) -> tuple[np.ndarray, bool]:
    if input_path.suffix.lower() == ".gif":
        with Image.open(input_path) as gif_image:
            frame = gif_image.convert("RGB")
            image = cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR)
    else:
        image = cv2.imdecode(np.fromfile(input_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)

    if image is None:
        raise RuntimeError(f"Failed to read image: {input_path}")

    was_gray = False
    if image.ndim == 2:
        was_gray = True
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.ndim == 3 and image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image, was_gray


def _normalize_output_suffix(value: str) -> str:
    suffix = value.lower().lstrip(".")
    return "jpeg" if suffix == "jpg" else suffix


def _encode_params(suffix: str, quality_mode: str) -> list[int]:
    mode = (quality_mode or "fast_auto").lower()
    if suffix in {".jpg", ".jpeg"}:
        quality = 82 if mode == "fast_auto" else 90 if mode == "quality_auto" else 95
        return [cv2.IMWRITE_JPEG_QUALITY, quality]
    if suffix == ".webp":
        quality = 80 if mode == "fast_auto" else 88 if mode == "quality_auto" else 95
        return [cv2.IMWRITE_WEBP_QUALITY, quality]
    return []


def _write_image(output_path: Path, image: np.ndarray, was_gray: bool, *, quality_mode: str = "fast_auto") -> None:
    final = image
    if was_gray and final.ndim == 3:
        final = cv2.cvtColor(final, cv2.COLOR_BGR2GRAY)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.lower()
    if suffix == ".gif":
        output_path = output_path.with_suffix(".png")
        suffix = ".png"
    params = _encode_params(suffix, quality_mode)
    ok, encoded = cv2.imencode(suffix, final, params)
    if not ok:
        raise RuntimeError(f"Failed to encode image: {output_path}")
    encoded.tofile(output_path)


def _write_passthrough_image(input_path: Path, output_path: Path, *, quality_mode: str = "fast_auto") -> None:
    image, was_gray = _read_image(input_path)
    _write_image(output_path, image, was_gray, quality_mode=quality_mode)


def _run_enhancer(image: np.ndarray, options: EnhanceOptions, enhancer_name: str | None) -> np.ndarray:
    enhancer = get_enhancer(enhancer_name if enhancer_name not in {"", "auto"} else None)
    return enhancer.enhance(image, options)


def _run_candidate(image: np.ndarray, attempt: EnhanceAttempt, page_metrics: dict[str, object]) -> np.ndarray:
    preprocessed = _preprocess_for_ai(image, attempt.options, page_metrics)
    enhanced = _run_enhancer(preprocessed, attempt.options, attempt.enhancer)
    return cv2.bilateralFilter(enhanced, d=5, sigmaColor=12, sigmaSpace=12)


def _preprocess_for_ai(image: np.ndarray, options: EnhanceOptions, page_metrics: dict[str, object]) -> np.ndarray:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    l_channel = cv2.normalize(l_channel, None, 0, 255, cv2.NORM_MINMAX)
    l_channel = cv2.fastNlMeansDenoising(l_channel, None, h=4 + max(options.noise, 0))
    if (
        page_metrics.get("pdf_source_mode") == "extract"
        and (
            page_metrics.get("page_profile") == "low_quality_scan"
            or float(page_metrics.get("blockiness") or 0.0) >= 10.0
        )
    ):
        l_channel = cv2.medianBlur(l_channel, 3)
    bright = np.percentile(l_channel, 97)
    if bright > 0:
        scale = min(255.0 / bright, 1.08)
        l_channel = np.clip(l_channel.astype(np.float32) * scale, 0, 255).astype(np.uint8)
    return cv2.cvtColor(cv2.merge((l_channel, a_channel, b_channel)), cv2.COLOR_LAB2BGR)


def _build_attempts(
    *,
    page_profile: str,
    strategy: str,
    requested_enhancer: str | None,
    base_options: EnhanceOptions,
    page_metrics: dict[str, object],
) -> list[EnhanceAttempt]:
    if requested_enhancer and requested_enhancer not in {"", "auto"}:
        return [EnhanceAttempt(requested_enhancer, base_options, "explicit enhancer request")]

    compat = strategy == "legacy_compatible"
    scale = base_options.scale
    pdf_source_mode = str(page_metrics.get("pdf_source_mode") or "")
    has_vector = bool(page_metrics.get("pdf_has_vector_content"))
    if page_profile == "color_illustration":
        attempts = [
            EnhanceAttempt("realesrgan-anime", EnhanceOptions(mode="standard", scale=scale, noise=0, tta=False, model=base_options.model), "anime color primary"),
            EnhanceAttempt("waifu2x", EnhanceOptions(mode="standard", scale=scale, noise=0, tta=False, model=base_options.model), "ai downgrade to waifu2x"),
        ]
    elif pdf_source_mode == "render" and page_profile in {"lineart_bw", "text_heavy"}:
        attempts = [
            EnhanceAttempt("waifu2x", EnhanceOptions(mode="conservative", scale=scale, noise=0, tta=False, model="models-cunet"), "pdf render lineart primary"),
            EnhanceAttempt("waifu2x", EnhanceOptions(mode="conservative", scale=scale, noise=-1, tta=False, model="models-cunet"), "pdf render lineart retry"),
            EnhanceAttempt("realesrgan-anime", EnhanceOptions(mode="conservative", scale=scale, noise=0, tta=False, model=base_options.model), "alternate ai retry"),
        ]
    elif page_profile == "low_quality_scan":
        attempts = [
            EnhanceAttempt("waifu2x", EnhanceOptions(mode="conservative", scale=scale, noise=2, tta=False, model="models-cunet"), "scan-safe primary"),
            EnhanceAttempt("waifu2x", EnhanceOptions(mode="conservative", scale=scale, noise=1, tta=False, model="models-cunet"), "scan-safe retry"),
            EnhanceAttempt("realesrgan-anime", EnhanceOptions(mode="conservative", scale=scale, noise=0, tta=False, model=base_options.model), "alternate ai retry"),
        ]
    elif page_profile == "halftone_gray":
        attempts = [
            EnhanceAttempt("waifu2x", EnhanceOptions(mode="conservative", scale=scale, noise=0, tta=False, model="models-cunet"), "halftone-safe primary"),
            EnhanceAttempt("waifu2x", EnhanceOptions(mode="conservative", scale=scale, noise=-1, tta=False, model="models-cunet"), "halftone-safe retry"),
            EnhanceAttempt("realesrgan-anime", EnhanceOptions(mode="conservative", scale=scale, noise=0, tta=False, model=base_options.model), "alternate ai retry"),
        ]
    elif page_profile == "text_heavy":
        attempts = [
            EnhanceAttempt("waifu2x", EnhanceOptions(mode="conservative", scale=scale, noise=0, tta=False, model="models-cunet"), "text-safe primary"),
            EnhanceAttempt("waifu2x", EnhanceOptions(mode="conservative", scale=scale, noise=-1, tta=False, model="models-cunet"), "text-safe retry"),
            EnhanceAttempt("realesrgan-anime", EnhanceOptions(mode="conservative", scale=scale, noise=0, tta=False, model=base_options.model), "alternate ai retry"),
        ]
    else:
        attempts = [
            EnhanceAttempt("waifu2x", EnhanceOptions(mode="standard", scale=scale, noise=1, tta=False, model="models-cunet"), "lineart primary"),
            EnhanceAttempt("waifu2x", EnhanceOptions(mode="conservative", scale=scale, noise=0, tta=False, model="models-cunet"), "lineart retry"),
            EnhanceAttempt("realesrgan-anime", EnhanceOptions(mode="standard", scale=scale, noise=0, tta=False, model=base_options.model), "alternate ai retry"),
        ]

    if has_vector:
        attempts = [
            EnhanceAttempt(
                item.enhancer,
                EnhanceOptions(mode="conservative", scale=item.options.scale, noise=min(item.options.noise, 0), tta=False, model=item.options.model),
                f"{item.reason} (vector-safe)",
            )
            for item in attempts
        ]

    return attempts


def _validate_candidate(*, original: np.ndarray, candidate: np.ndarray, page_profile: str, page_metrics: dict[str, object]) -> str | None:
    original_gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
    candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
    target_size = (candidate_gray.shape[1], candidate_gray.shape[0])
    original_up = cv2.resize(original_gray, target_size, interpolation=cv2.INTER_CUBIC)

    orig_edges = _edge_density(original_up)
    cand_edges = _edge_density(candidate_gray)
    orig_block = _blockiness(original_up)
    cand_block = _blockiness(candidate_gray)
    orig_mean = float(original_up.mean())
    cand_mean = float(candidate_gray.mean())
    orig_bg = float(np.percentile(original_up, 95))
    cand_bg = float(np.percentile(candidate_gray, 95))
    orig_sharpness = float(cv2.Laplacian(original_up, cv2.CV_64F).var())
    cand_sharpness = float(cv2.Laplacian(candidate_gray, cv2.CV_64F).var())

    if cand_mean < orig_mean * 0.72 and cand_bg < orig_bg * 0.88:
        return "output too dark"
    if cand_mean > min(255.0, orig_mean * 1.28 + 12) and cand_bg > min(255.0, orig_bg * 1.08 + 8):
        return "output overexposed"
    if page_metrics.get("pdf_source_mode") == "render" and cand_edges < orig_edges * 0.82:
        return "pdf render edge clarity regressed"
    if page_metrics.get("pdf_source_mode") == "extract" and float(page_metrics.get("blockiness") or 0.0) >= 10.0 and cand_block > orig_block * 1.25 + 1.0:
        return "pdf extract artifacts increased"
    if page_metrics.get("pdf_has_vector_content") and cand_sharpness > max(orig_sharpness * 3.5, orig_sharpness + 2200):
        return "pdf vector page oversharpened"
    if page_profile in {"lineart_bw", "text_heavy"} and cand_edges < orig_edges * 0.84:
        return "edge clarity regressed"
    if page_profile == "halftone_gray" and cand_block > orig_block * 1.35 + 1.5:
        return "halftone artifacts increased"
    if cand_sharpness > max(orig_sharpness * 4.0, orig_sharpness + 2800):
        return "oversharpened"
    return None


def _edge_density(gray: np.ndarray) -> float:
    edges = cv2.Canny(gray, 80, 180)
    return float(np.count_nonzero(edges) / max(edges.size, 1))


def _blockiness(gray: np.ndarray) -> float:
    if gray.shape[0] < 16 or gray.shape[1] < 16:
        return 0.0
    boundary_cols = np.arange(8, gray.shape[1], 8)
    boundary_rows = np.arange(8, gray.shape[0], 8)
    vertical = np.abs(gray[:, boundary_cols] - gray[:, boundary_cols - 1]).mean() if boundary_cols.size else 0.0
    horizontal = np.abs(gray[boundary_rows, :] - gray[boundary_rows - 1, :]).mean() if boundary_rows.size else 0.0
    return float((vertical + horizontal) / 2.0)
