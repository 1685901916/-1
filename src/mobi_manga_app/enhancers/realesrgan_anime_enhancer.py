from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import BaseEnhancer, EnhanceOptions

_MODEL_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-animevideov3.pth"
_MODEL_FILENAME = "realesr-animevideov3.pth"

# 本地模型搜索路径（优先级从高到低）
_LOCAL_CANDIDATES = [
    Path(__file__).parent.parent.parent.parent / ".models" / _MODEL_FILENAME,
    Path.home() / ".cache" / "realesrgan" / _MODEL_FILENAME,
    Path(__file__).parent / _MODEL_FILENAME,
]


def _local_model_path() -> Path | None:
    """返回已存在的本地模型路径（至少 1 MB），找不到返回 None。"""
    for p in _LOCAL_CANDIDATES:
        if p.exists() and p.stat().st_size > 1024 * 1024:
            return p
    return None


def _model_path_for_loader() -> str:
    """给 RealESRGANer 用的路径：本地优先，否则用 URL（需网络）。"""
    local = _local_model_path()
    return str(local) if local else _MODEL_URL


class RealESRGANAnimeEnhancer(BaseEnhancer):
    """Real-ESRGAN AnimeVideo model（需要 realesrgan + basicsr）。

    is_available() 同时检查：
      1. realesrgan / basicsr 库是否已安装
      2. 本地模型文件是否存在（≥1MB）
    两者都满足才返回 True，避免执行时才发现模型文件缺失。
    """

    def __init__(self) -> None:
        self._model = None

    @property
    def name(self) -> str:
        return "realesrgan-anime"

    @property
    def requires_gpu(self) -> bool:
        return False

    def is_available(self) -> bool:
        # 先检查 Python 包
        try:
            from . import _fix_basicsr              # noqa: F401
            from realesrgan import RealESRGANer     # noqa: F401
            from realesrgan.archs.srvgg_arch import SRVGGNetCompact  # noqa: F401
        except Exception:
            return False
        # 再检查本地模型文件（有文件才显示可用）
        return _local_model_path() is not None

    def model_file_hint(self) -> str:
        """返回模型文件应放置的首选路径（供前端展示提示）。"""
        return str(_LOCAL_CANDIDATES[0])

    def enhance(self, image: np.ndarray, options: EnhanceOptions) -> np.ndarray:
        import cv2
        if self._model is None:
            self._load_model()
        # base.py 已保证传入 BGR 3通道
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        output, _ = self._model.enhance(rgb, outscale=options.scale)
        return cv2.cvtColor(output, cv2.COLOR_RGB2BGR)

    def _load_model(self) -> None:
        from . import _fix_basicsr              # noqa: F401
        from realesrgan import RealESRGANer
        from realesrgan.archs.srvgg_arch import SRVGGNetCompact

        model = SRVGGNetCompact(
            num_in_ch=3, num_out_ch=3, num_feat=64,
            num_conv=16, upscale=4, act_type="prelu",
        )
        self._model = RealESRGANer(
            scale=4,
            model_path=_model_path_for_loader(),
            model=model,
            tile=512,       # 分块处理，避免显存不足
            tile_pad=10,
            pre_pad=0,
            half=False,
        )

