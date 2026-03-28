from __future__ import annotations

import numpy as np

from .base import BaseEnhancer, EnhanceOptions


class RealESRGANEnhancer(BaseEnhancer):
    """Real-ESRGAN AI model enhancer"""

    def __init__(self):
        self._model = None

    @property
    def name(self) -> str:
        return "realesrgan"

    @property
    def requires_gpu(self) -> bool:
        return False

    def is_available(self) -> bool:
        try:
            from . import _fix_basicsr
            from realesrgan import RealESRGANer
            return True
        except Exception:
            return False

    def enhance(self, image: np.ndarray, options: EnhanceOptions) -> np.ndarray:
        import cv2
        if self._model is None:
            self._load_model()

        # base.py 已保证传入 BGR 3通道
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        output, _ = self._model.enhance(rgb, outscale=options.scale)
        return cv2.cvtColor(output, cv2.COLOR_RGB2BGR)

    def _load_model(self):
        from . import _fix_basicsr  # noqa: F401
        from realesrgan import RealESRGANer
        from basicsr.archs.rrdbnet_arch import RRDBNet

        model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=6, num_grow_ch=32, scale=4)

        self._model = RealESRGANer(
            scale=4,
            model_path="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-animevideov3.pth",
            model=model,
            tile=512,
            tile_pad=10,
            pre_pad=0,
            half=False,
        )
