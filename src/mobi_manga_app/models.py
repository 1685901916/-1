from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class InputFormat(StrEnum):
    MOBI = "mobi"
    PDF = "pdf"
    CBZ = "cbz"
    ZIP = "zip"
    EPUB = "epub"
    FOLDER = "folder"


class OutputFormat(StrEnum):
    CBZ = "cbz"
    ZIP = "zip"
    EPUB = "epub"
    MOBI = "mobi"
    PDF = "pdf"


class JobStage(StrEnum):
    IMPORT = "import"
    ANALYZE = "analyze"
    ENHANCE = "enhance"
    OPTIMIZE = "optimize"
    PACKAGE = "package"
    EXPORT = "export"


@dataclass(slots=True)
class ExportOption:
    id: str
    label: str
    description: str
    recommended_for: str


@dataclass(slots=True)
class PipelineStep:
    id: str
    label: str
    description: str
    outputs: list[str]


@dataclass(slots=True)
class SourceBook:
    name: str
    path: str
    format: str
    size_mb: float
    can_split: bool = True
    can_enhance: bool = True
    can_export: bool = True
    can_merge: bool = True
    has_pages: bool = False
    has_pages_ai: bool = False
    latest_job_id: str | None = None
    latest_stage: str | None = None
    latest_status: str | None = None


@dataclass(slots=True)
class JobRecord:
    id: str
    name: str
    source_name: str
    source_path: str
    workspace: str
    stage: str
    status: str
    output_dir: str = ""
    keep_original_pages: bool = True
    keep_enhanced_pages: bool = True
    progress: int = 0
    progress_label: str = ""
    page_count: int | None = None
    outputs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    error_detail: str | None = None
    started_at: str | None = None
    updated_at: str | None = None


@dataclass(slots=True)
class DashboardData:
    product_name: str
    tagline: str
    source_root: str
    default_output_root: str
    export_options: list[ExportOption]
    pipeline_steps: list[PipelineStep]
    source_books: list[SourceBook]
    jobs: list[JobRecord]
    design_system: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_name": self.product_name,
            "tagline": self.tagline,
            "source_root": self.source_root,
            "default_output_root": self.default_output_root,
            "export_options": [asdict(item) for item in self.export_options],
            "pipeline_steps": [asdict(item) for item in self.pipeline_steps],
            "source_books": [asdict(item) for item in self.source_books],
            "jobs": [asdict(item) for item in self.jobs],
            "design_system": self.design_system,
        }


def file_size_mb(path: Path) -> float:
    return round(path.stat().st_size / (1024 * 1024), 2)
