from __future__ import annotations

import importlib.util

import cv2
import numpy as np
from PIL import Image

from .base import BaseEnhancer, EnhanceOptions


class Waifu2xEnhancer(BaseEnhancer):
    """Real Waifu2x enhancer using waifu2x-ncnn-vulkan-python."""

    MODEL_OPTIONS = ["models-cunet", "models-upconv_7_anime_style_art_rgb"]

    def __init__(self):
        self._upscaler = None
        self._last_key = None

    @property
    def name(self) -> str:
        return "waifu2x"

    @property
    def requires_gpu(self) -> bool:
        return False

    def is_available(self) -> bool:
        return importlib.util.find_spec("waifu2x_ncnn_py") is not None

    def option_schema(self) -> dict[str, object]:
        return {
            "noise": {"type": "int", "default": 1, "choices": [-1, 0, 1, 2, 3]},
            "tta": {"type": "bool", "default": False},
            "model": {"type": "str", "default": "models-cunet", "choices": self.MODEL_OPTIONS},
        }

    def enhance(self, image: np.ndarray, options: EnhanceOptions) -> np.ndarray:
        from waifu2x_ncnn_py import Waifu2x

        waifu2x_scale = 2 if options.scale >= 1.5 else 1
        model_name = options.model if options.model in self.MODEL_OPTIONS else "models-cunet"
        key = (waifu2x_scale, options.noise, options.tta, model_name)

        if self._upscaler is None or self._last_key != key:
            self._upscaler = Waifu2x(
                gpuid=0,
                scale=waifu2x_scale,
                noise=options.noise,
                model=model_name,
                tta_mode=options.tta,
            )
            self._last_key = key

        rgb = image[:, :, ::-1].copy()
        pil_img = Image.fromarray(rgb)
        enhanced_pil = self._upscaler.process_pil(pil_img)
        result = np.array(enhanced_pil)

        orig_h, orig_w = image.shape[:2]
        target_w = int(round(orig_w * options.scale))
        target_h = int(round(orig_h * options.scale))
        result_h, result_w = result.shape[:2]

        if result_w != target_w or result_h != target_h:
            bgr = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)
            return cv2.resize(bgr, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)

        return result[:, :, ::-1].copy()
