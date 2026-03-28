from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class StoredJob:
    id: str
    name: str
    source_name: str
    source_path: str
    workspace: str
    output_dir: str
    output_formats: list[str]
    target_device: str
    keep_original_pages: bool = True
    keep_enhanced_pages: bool = True
    strategy: str = "quality_auto"
    enhancer: str = ""
    enhance_scale: float = 1.5
    waifu2x_noise: int = 1
    waifu2x_tta: bool = False
    waifu2x_model: str = "models-cunet"
    pdf_mode: str = "auto"
    pdf_quality_mode: str = "fast_auto"
    pdf_image_format: str = "jpg"
    pdf_render_dpi: int = 300
    stage: str = "import"
    status: str = "queued"
    progress: int = 0
    progress_label: str = "waiting"
    page_count: int | None = None
    outputs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    enhancement_profile_counts: dict[str, int] = field(default_factory=dict)
    page_enhancements: list[dict[str, Any]] = field(default_factory=list)
    model_availability: dict[str, bool] = field(default_factory=dict)
    error_detail: str | None = None
    started_at: str | None = None
    updated_at: str | None = None


class JobStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.file = self.root / "jobs.json"

    def load(self) -> list[StoredJob]:
        if not self.file.exists():
            return []

        import time

        payload = []
        for attempt in range(3):
            try:
                raw = self.file.read_text(encoding="utf-8")
                if not raw.strip():
                    return []
                payload = json.loads(raw)
                break
            except json.JSONDecodeError:
                if attempt == 2:
                    return []
                time.sleep(0.1)

        jobs: list[StoredJob] = []
        for item in payload:
            item.setdefault("source_name", item.get("name", ""))
            item.setdefault("progress", 0)
            item.setdefault("progress_label", "waiting")
            item.setdefault("logs", [])
            item.setdefault("error_detail", None)
            item.setdefault("started_at", None)
            item.setdefault("updated_at", None)
            item.setdefault("keep_original_pages", True)
            item.setdefault("keep_enhanced_pages", True)
            item.setdefault("strategy", "quality_auto")
            item.setdefault("enhancer", "")
            item.setdefault("enhance_scale", 1.5)
            item.setdefault("waifu2x_noise", 1)
            item.setdefault("waifu2x_tta", False)
            item.setdefault("waifu2x_model", "models-cunet")
            item.setdefault("pdf_quality_mode", "fast_auto")
            item.setdefault("enhancement_profile_counts", {})
            item.setdefault("page_enhancements", [])
            item.setdefault("model_availability", {})
            jobs.append(StoredJob(**item))
        return jobs

    def save(self, jobs: list[StoredJob]) -> None:
        temp_file = self.root / f"jobs_temp_{uuid.uuid4().hex}.json"
        try:
            temp_file.write_text(
                json.dumps([asdict(item) for item in jobs], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp_file.replace(self.file)
        finally:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    def list(self) -> list[StoredJob]:
        return self.load()

    def get(self, job_id: str) -> StoredJob | None:
        for job in self.load():
            if job.id == job_id:
                return job
        return None

    def upsert(self, job: StoredJob) -> StoredJob:
        jobs = self.load()
        updated = False
        for index, current in enumerate(jobs):
            if current.id == job.id:
                jobs[index] = job
                updated = True
                break
        if not updated:
            jobs.append(job)
        self.save(jobs)
        return job

    def delete(self, job_id: str) -> bool:
        jobs = self.load()
        filtered = [job for job in jobs if job.id != job_id]
        if len(filtered) == len(jobs):
            return False
        self.save(filtered)
        return True

    def create(
        self,
        *,
        name: str,
        source_name: str,
        source_path: str,
        workspace_root: str,
        output_dir: str,
        output_formats: list[str],
        target_device: str,
        keep_original_pages: bool = True,
        keep_enhanced_pages: bool = True,
        strategy: str = "quality_auto",
        enhancer: str = "",
        enhance_scale: float = 1.5,
        waifu2x_noise: int = 1,
        waifu2x_tta: bool = False,
        waifu2x_model: str = "models-cunet",
        pdf_mode: str = "auto",
        pdf_quality_mode: str = "fast_auto",
        pdf_image_format: str = "jpg",
        pdf_render_dpi: int = 300,
    ) -> StoredJob:
        job_id = uuid.uuid4().hex[:10]
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "job"
        workspace = str(Path(workspace_root) / f"{job_id}_{safe_name}")
        job = StoredJob(
            id=job_id,
            name=name,
            source_name=source_name,
            source_path=source_path,
            workspace=workspace,
            output_dir=output_dir,
            output_formats=output_formats,
            target_device=target_device,
            keep_original_pages=keep_original_pages,
            keep_enhanced_pages=keep_enhanced_pages,
            strategy=strategy,
            enhancer=enhancer,
            enhance_scale=enhance_scale,
            waifu2x_noise=waifu2x_noise,
            waifu2x_tta=waifu2x_tta,
            waifu2x_model=waifu2x_model,
            pdf_mode=pdf_mode,
            pdf_quality_mode=pdf_quality_mode,
            pdf_image_format=pdf_image_format,
            pdf_render_dpi=pdf_render_dpi,
            updated_at=datetime.now().isoformat(timespec="seconds"),
        )
        return self.upsert(job)


def job_to_payload(job: StoredJob) -> dict[str, Any]:
    return asdict(job)
