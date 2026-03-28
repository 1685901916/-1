from __future__ import annotations

import cv2
import numpy as np

from .base import BaseEnhancer, EnhanceOptions


class OpenCVEnhancer(BaseEnhancer):
    """Basic OpenCV-based enhancer (no AI model required)"""

    @property
    def name(self) -> str:
        return "opencv"

    @property
    def requires_gpu(self) -> bool:
        return False

    def is_available(self) -> bool:
        return True

    def enhance(self, image: np.ndarray, options: EnhanceOptions) -> np.ndarray:
        # base.py 已统一转为 BGR 3通道，这里不需要再判断灰度/BGRA
        return self._enhance_color(image, options)

    def _enhance_gray(self, gray: np.ndarray, options: EnhanceOptions) -> np.ndarray:
        """保留备用：仅在直接调用时使用"""
        sigma, sharpen_amount, contrast = self._mode_values(options.mode)
        denoised = cv2.fastNlMeansDenoising(gray, None, h=4 + sigma, templateWindowSize=7, searchWindowSize=21)
        if options.scale != 1.0:
            denoised = cv2.resize(denoised, None, fx=options.scale, fy=options.scale, interpolation=cv2.INTER_LANCZOS4)
        clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))
        boosted = clahe.apply(denoised)
        # contrast=1.0 时直接用 boosted 会丢失暗部，用0.6/0.4混合保留原始细节
        blend = min(contrast, 0.7)
        merged = cv2.addWeighted(boosted, blend, denoised, 1.0 - blend, 0)
        return self._unsharp_mask(merged, sigma=max(1, sigma // 2), amount=sharpen_amount)

    def _enhance_color(self, image: np.ndarray, options: EnhanceOptions) -> np.ndarray:
        sigma, sharpen_amount, contrast = self._mode_values(options.mode)
        denoised = cv2.fastNlMeansDenoisingColored(image, None, h=3 + sigma, hColor=3 + sigma, templateWindowSize=7, searchWindowSize=21)
        if options.scale != 1.0:
            denoised = cv2.resize(denoised, None, fx=options.scale, fy=options.scale, interpolation=cv2.INTER_LANCZOS4)
        lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        l_channel = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8)).apply(l_channel)
        rebuilt = cv2.cvtColor(cv2.merge((l_channel, a_channel, b_channel)), cv2.COLOR_LAB2BGR)
        # contrast=1.0 时不能直接只用 rebuilt，会让暗部细节消失变成纯黑
        # 用0.6/0.4混合：CLAHE 提亮 + 原始去噪版保留暗部层次
        blend = min(contrast, 0.7)
        merged = cv2.addWeighted(rebuilt, blend, denoised, 1.0 - blend, 0)
        return self._unsharp_mask(merged, sigma=max(1, sigma // 2), amount=sharpen_amount)

    @staticmethod
    def _mode_values(mode: str) -> tuple[int, float, float]:
        table = {
            "conservative": (4, 0.35, 0.9),
            "standard": (5, 0.55, 1.0),
            "strong": (6, 0.75, 1.12),
        }
        if mode not in table:
            raise ValueError(f"Unsupported enhancement mode: {mode}")
        return table[mode]

    @staticmethod
    def _unsharp_mask(image: np.ndarray, sigma: int, amount: float) -> np.ndarray:
        blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=sigma)
        return cv2.addWeighted(image, 1.0 + amount, blurred, -amount, 0)
