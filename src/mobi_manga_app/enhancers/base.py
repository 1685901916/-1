from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(slots=True)
class EnhanceOptions:
    mode: str = "standard"
    scale: float = 2.0
    noise: int = 1
    tta: bool = False
    model: str = "models-cunet"


class BaseEnhancer(ABC):
    """Base class for all image enhancers"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Enhancer name"""
        pass

    @property
    @abstractmethod
    def requires_gpu(self) -> bool:
        """Whether this enhancer requires GPU"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this enhancer can be used"""
        pass

    @abstractmethod
    def enhance(self, image: np.ndarray, options: EnhanceOptions) -> np.ndarray:
        """Enhance a single image"""
        pass

    def enhance_file(self, input_path: Path, output_path: Path, options: EnhanceOptions) -> None:
        """Enhance an image file (default implementation)"""
        import cv2
        from PIL import Image

        if input_path.suffix.lower() == ".gif":
            with Image.open(input_path) as gif_image:
                frame = gif_image.convert("RGB")
                # GIF → BGR 3通道
                image = cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR)
        else:
            # IMREAD_UNCHANGED：灰度图→ndim=2, 彩色→ndim=3(BGR), RGBA→ndim=3(BGRA)
            image = cv2.imdecode(np.fromfile(input_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)

        if image is None:
            raise RuntimeError(f"Failed to read image: {input_path}")

        # 统一转为 BGR 3通道送入 enhancer，避免各 enhancer 重复处理灰度/BGRA 分支
        was_gray = False
        if image.ndim == 2:
            # 灰度图：记录标志，转3通道处理，输出时再转回
            was_gray = True
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif image.ndim == 3 and image.shape[2] == 4:
            # BGRA → BGR（丢弃透明通道）
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        # 其他情况已经是 BGR 3通道

        enhanced = self.enhance(image, options)

        # 如果原图是灰度，输出也转回灰度（保持文件体积小，色调一致）
        if was_gray and enhanced.ndim == 3:
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_suffix = output_path.suffix.lower()
        if output_suffix == ".gif":
            output_path = output_path.with_suffix(".png")
            output_suffix = ".png"

        ok, encoded = cv2.imencode(output_suffix, enhanced)
        if not ok:
            raise RuntimeError(f"Failed to encode image: {output_path}")
        encoded.tofile(output_path)
