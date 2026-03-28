from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(slots=True)
class CommandSpec:
    name: str
    command: list[str] | None
    source: str
    script_path: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.command or self.script_path)


@dataclass(slots=True)
class ToolRegistry:
    kindleunpack: CommandSpec
    kcc: CommandSpec


def _env_or_which(env_name: str, candidates: Sequence[str], display_name: str) -> CommandSpec:
    env_value = os.getenv(env_name)
    if env_value:
        path = Path(env_value)
        if path.suffix.lower() == ".py":
            return CommandSpec(display_name, [sys.executable, str(path)], f"env:{env_name}", script_path=str(path))
        return CommandSpec(display_name, [env_value], f"env:{env_name}")

    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return CommandSpec(display_name, [resolved], f"path:{candidate}")

    return CommandSpec(display_name, None, "missing")


def _local_repo_command(relative_script: str, display_name: str) -> CommandSpec | None:
    candidates: list[tuple[Path, str]] = []
    repo_root = Path(__file__).resolve().parents[2]
    candidates.append((repo_root / relative_script, f"repo:{relative_script}"))

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundle_root = Path(sys._MEIPASS)
        candidates.append((bundle_root / relative_script, f"bundle:{relative_script}"))

    for script, source in candidates:
        if script.exists():
            if getattr(sys, "frozen", False):
                return CommandSpec(display_name, None, source, script_path=str(script))
            return CommandSpec(display_name, [sys.executable, str(script)], source, script_path=str(script))
    return None


def discover_tools() -> ToolRegistry:
    local_kindleunpack = _local_repo_command("tools/kindleunpack_cli.py", "KindleUnpack")
    return ToolRegistry(
        kindleunpack=local_kindleunpack
        or _env_or_which(
            "KINDLEUNPACK_CMD",
            ["kindleunpack", "kindleunpack.py"],
            "KindleUnpack",
        ),
        kcc=_env_or_which(
            "KCC_CMD",
            ["kcc-c2e", "kcc_c2e", "kcc"],
            "KCC",
        ),
    )
