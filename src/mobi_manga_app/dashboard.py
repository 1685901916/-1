from __future__ import annotations

from pathlib import Path

from .job_store import JobStore
from .models import DashboardData, ExportOption, JobRecord, OutputFormat, PipelineStep, SourceBook, file_size_mb
from .utils import iter_image_files


DEFAULT_SOURCE_ROOT = Path.cwd() / ".work" / "sources"
SUPPORTED_FILE_SUFFIXES = {".mobi", ".cbz", ".zip", ".pdf", ".epub"}


def _read_design_system(repo_root: Path) -> dict[str, object]:
    for candidate in (repo_root / "design-system").glob("*/MASTER.md"):
        return {
            "master_path": str(candidate),
            "summary": candidate.read_text(encoding="utf-8", errors="ignore")[:2000],
        }
    return {}


def _is_image_folder(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        next(iter_image_files(path))
        return True
    except StopIteration:
        return False


def _stage_rank(stage: str) -> int:
    order = {
        "split": 1,
        "import": 1,
        "analyze": 2,
        "enhance_module": 3,
        "enhance": 3,
        "optimize": 4,
        "export_module": 5,
        "package": 5,
        "export": 6,
    }
    return order.get(stage, 0)


def _status_rank(status: str) -> int:
    order = {
        "running": 4,
        "ready": 3,
        "queued": 2,
        "processed": 1,
        "failed": 0,
    }
    return order.get(status, 0)


def _job_priority(job: JobRecord) -> tuple[int, int, int, int, int]:
    return (
        1 if job.status == "running" else 0,
        1 if job.status == "failed" else 0,
        int((job.updated_at or "").replace("-", "").replace(":", "").replace("T", "").replace(".", "") or 0),
        _status_rank(job.status),
        _stage_rank(job.stage),
    )


def _job_is_visible(item) -> bool:
    return bool(item.outputs) or Path(item.source_path).exists()


def _stored_jobs(repo_root: Path) -> list[JobRecord]:
    store = JobStore(repo_root / ".work" / "appdata")
    merged: dict[str, JobRecord] = {}

    for item in store.list():
        if not _job_is_visible(item):
            continue

        source_name = item.source_name or item.name
        current = JobRecord(
            id=item.id,
            name=source_name,
            source_name=source_name,
            source_path=item.source_path,
            workspace=item.workspace,
            output_dir=item.output_dir,
            keep_original_pages=item.keep_original_pages,
            keep_enhanced_pages=item.keep_enhanced_pages,
            stage=item.stage,
            status=item.status,
            progress=item.progress,
            progress_label=item.progress_label or ("已完成" if item.status == "ready" else "等待执行"),
            page_count=item.page_count,
            outputs=item.outputs,
            notes=item.notes,
            logs=item.logs,
            error_detail=item.error_detail,
            started_at=item.started_at,
            updated_at=item.updated_at,
        )

        previous = merged.get(source_name)
        if previous is None or _job_priority(current) > _job_priority(previous):
            merged[source_name] = current

    return sorted(merged.values(), key=lambda job: (_stage_rank(job.stage), job.updated_at or ""), reverse=True)


def _source_books(source_root: Path, jobs: list[JobRecord]) -> list[SourceBook]:
    if not source_root.exists():
        return []

    latest_by_source = {job.source_name: job for job in jobs}
    books: list[SourceBook] = []
    seen: set[str] = set()

    def build_source_book(path: Path, *, name: str, format_name: str) -> SourceBook:
        job = latest_by_source.get(name) or latest_by_source.get(path.name)
        outputs = [Path(item) for item in (job.outputs if job else [])]
        has_pages = any(item.name == "pages" and item.exists() for item in outputs)
        has_pages_ai = any(item.name == "pages_ai" and item.exists() for item in outputs)
        return SourceBook(
            name=name,
            path=str(path),
            format=format_name,
            size_mb=file_size_mb(path),
            has_pages=has_pages,
            has_pages_ai=has_pages_ai,
            latest_job_id=job.id if job else None,
            latest_stage=job.stage if job else None,
            latest_status=job.status if job else None,
        )

    if _is_image_folder(source_root):
        books.append(build_source_book(source_root, name=source_root.name, format_name="folder"))
        seen.add(str(source_root.resolve()))

    for path in sorted(source_root.rglob("*")):
        resolved = str(path.resolve())
        if resolved in seen:
            continue

        if path.is_file() and path.suffix.lower() in SUPPORTED_FILE_SUFFIXES:
            books.append(
                build_source_book(
                    path,
                    name=str(path.relative_to(source_root)),
                    format_name=path.suffix.lower().lstrip("."),
                )
            )
            seen.add(resolved)
            continue

        if _is_image_folder(path):
            books.append(
                build_source_book(
                    path,
                    name=str(path.relative_to(source_root)),
                    format_name="folder",
                )
            )
            seen.add(resolved)

    return books


def build_dashboard_data(
    repo_root: Path,
    source_root: Path = DEFAULT_SOURCE_ROOT,
    default_output_root: Path | None = None,
) -> DashboardData:
    jobs = _stored_jobs(repo_root)
    return DashboardData(
        product_name="漫画画质提升",
        tagline="本地漫画拆分、画质增强与多格式导出工作台",
        source_root=str(source_root),
        default_output_root=str(default_output_root or (repo_root / ".work" / "outputs")),
        export_options=[
            ExportOption(
                id=OutputFormat.CBZ,
                label="CBZ",
                description="高兼容漫画归档格式，适合平板阅读与整理收藏。",
                recommended_for="阅读器与归档",
            ),
            ExportOption(
                id=OutputFormat.ZIP,
                label="ZIP",
                description="与 CBZ 内容一致，适合手动检查与通用压缩流程。",
                recommended_for="兼容导出",
            ),
            ExportOption(
                id=OutputFormat.EPUB,
                label="EPUB",
                description="适合安卓平板与通用电子书阅读器，需要 KCC。",
                recommended_for="手机与平板",
            ),
            ExportOption(
                id=OutputFormat.MOBI,
                label="MOBI",
                description="适合 Kindle 设备，需要 KCC。",
                recommended_for="Kindle",
            ),
            ExportOption(
                id=OutputFormat.PDF,
                label="PDF",
                description="按图片页重新生成 PDF，适合分享、打印与快速预览。",
                recommended_for="分享与预览",
            ),
        ],
        pipeline_steps=[
            PipelineStep(
                id="split",
                label="导入拆分",
                description="把漫画文件或图片目录标准化为 pages 图片序列。",
                outputs=["pages/*"],
            ),
            PipelineStep(
                id="enhance_module",
                label="画质提升",
                description="读取 pages 或图片目录，输出增强后的 pages_ai。",
                outputs=["pages_ai/*"],
            ),
            PipelineStep(
                id="export_module",
                label="封装导出",
                description="把 pages_ai 或图片目录封装为 CBZ、ZIP、EPUB、MOBI、PDF。",
                outputs=["*.cbz", "*.zip", "*.epub", "*.mobi", "*.pdf", "manifest.json"],
            ),
        ],
        source_books=_source_books(source_root, jobs),
        jobs=jobs,
        design_system=_read_design_system(repo_root),
    )
