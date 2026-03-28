from __future__ import annotations

import threading
from typing import Type

from .base import BaseEnhancer
from .opencv_enhancer import OpenCVEnhancer

_ENHANCERS: dict[str, Type[BaseEnhancer]] = {}
_LOCK = threading.Lock()
_LOADED = False
_AUTO_PRIORITY = ["realesrgan-anime", "waifu2x"]
_LEGACY_ENHANCERS = {"opencv"}


def register_enhancer(enhancer_class: Type[BaseEnhancer]) -> None:
    instance = enhancer_class()
    _ENHANCERS[instance.name] = enhancer_class


def get_enhancer(name: str | None = None) -> BaseEnhancer:
    _ensure_enhancers_loaded()

    if name and name in _ENHANCERS:
        enhancer = _ENHANCERS[name]()
        if enhancer.is_available():
            return enhancer
        raise RuntimeError(f"Enhancer unavailable: {name}")
    elif name:
        raise RuntimeError(f"Unknown enhancer: {name}")

    for preferred in _AUTO_PRIORITY:
        if preferred in _ENHANCERS:
            enhancer = _ENHANCERS[preferred]()
            if enhancer.is_available():
                return enhancer

    raise RuntimeError("No available AI enhancer found. Install waifu2x or Real-ESRGAN.")


def list_enhancers() -> list[dict[str, object]]:
    _ensure_enhancers_loaded()
    ordered = [n for n in _AUTO_PRIORITY if n in _ENHANCERS]
    rest = [n for n in _ENHANCERS if n not in ordered]
    result = []
    for name in ordered + rest:
        try:
            enhancer = _ENHANCERS[name]()
            option_schema = {}
            if hasattr(enhancer, "option_schema"):
                option_schema = getattr(enhancer, "option_schema")() or {}
            result.append(
                {
                    "name": name,
                    "requires_gpu": enhancer.requires_gpu,
                    "available": enhancer.is_available(),
                    "options": option_schema,
                    "recommended": name not in _LEGACY_ENHANCERS,
                    "legacy": name in _LEGACY_ENHANCERS,
                }
            )
        except Exception:
            result.append(
                {
                    "name": name,
                    "requires_gpu": False,
                    "available": False,
                    "options": {},
                    "recommended": name not in _LEGACY_ENHANCERS,
                    "legacy": name in _LEGACY_ENHANCERS,
                }
            )
    return result


def _ensure_enhancers_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    with _LOCK:
        if _LOADED:
            return
        _LOADED = True

        try:
            from .realesrgan_anime_enhancer import RealESRGANAnimeEnhancer

            register_enhancer(RealESRGANAnimeEnhancer)
        except Exception:
            pass

        try:
            from .waifu2x_enhancer import Waifu2xEnhancer

            register_enhancer(Waifu2xEnhancer)
        except Exception:
            pass

        register_enhancer(OpenCVEnhancer)
