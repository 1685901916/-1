from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Workspace:
    root: Path

    @property
    def unpacked_dir(self) -> Path:
        return self.root / "unpacked"

    @property
    def pages_dir(self) -> Path:
        return self.root / "pages"

    @property
    def enhanced_dir(self) -> Path:
        return self.root / "enhanced"

    @property
    def optimized_dir(self) -> Path:
        return self.root / "optimized"

    @property
    def export_dir(self) -> Path:
        return self.root / "export"

    @property
    def analysis_file(self) -> Path:
        return self.root / "analysis.json"

    @property
    def pdf_split_meta_file(self) -> Path:
        return self.unpacked_dir / "pdf_split_meta.json"

    @property
    def manifest_file(self) -> Path:
        return self.root / "manifest.json"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.unpacked_dir.mkdir(parents=True, exist_ok=True)
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.enhanced_dir.mkdir(parents=True, exist_ok=True)
        self.optimized_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)
