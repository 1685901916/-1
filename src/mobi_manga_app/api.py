from __future__ import annotations

import argparse
import cgi
import json
import mimetypes
import os
import shutil
import threading
import traceback
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .dashboard import DEFAULT_SOURCE_ROOT, build_dashboard_data
from .job_store import JobStore, StoredJob, job_to_payload
from .merge import merge_sources
from .workflow import (
    run_analyze_only,
    run_enhance_only,
    run_export_module,
    run_export_only,
    run_full_pipeline,
    run_import_only,
    run_optimize_only,
    run_package_only,
    summarize_job_context,
)


def _touch(job: StoredJob, **updates: object) -> StoredJob:
    for key, value in updates.items():
        setattr(job, key, value)
    job.updated_at = datetime.now().isoformat(timespec="seconds")
    return job


def _append_logs(job: StoredJob, *lines: str) -> StoredJob:
    entries = [line for line in lines if line]
    if entries:
        job.logs = [*(job.logs or []), *entries][-300:]
    return job


def _format_exception(exc: Exception) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def _safe_uploaded_name(name: str) -> str:
    candidate = Path(name).name.strip()
    if not candidate:
        candidate = "imported_file"
    return candidate


def _safe_relative_name(name: str) -> Path:
    raw = (name or "").replace("\\", "/").strip("/")
    parts = [part for part in Path(raw).parts if part not in {"", ".", ".."}]
    if not parts:
        return Path("image.png")
    return Path(*parts)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    return json.loads(raw.decode("utf-8") or "{}")


def _run_in_background(store: JobStore, job: StoredJob, step: str) -> None:
    def worker() -> None:
        current = store.get(job.id) or job
        try:
            transitions = {
                "split": (18, "import", "提取图片"),
                "import": (10, "import", "Importing pages"),
                "analyze": (28, "analyze", "Analyzing pages"),
                "enhance_module": (56, "enhance", "画质提升"),
                "enhance": (50, "enhance", "Enhancing pages"),
                "optimize": (68, "optimize", "Preparing pages_ai"),
                "export_module": (88, "export", "封装导出"),
                "package": (84, "package", "Packaging outputs"),
                "export": (94, "export", "Writing manifest"),
            }
            runners = {
                "split": run_import_only,
                "import": run_import_only,
                "analyze": run_analyze_only,
                "enhance_module": run_enhance_only,
                "enhance": run_enhance_only,
                "optimize": run_optimize_only,
                "export_module": run_export_module,
                "package": run_package_only,
                "export": run_export_only,
            }

            if step == "full":
                _append_logs(current, "task start: full", *summarize_job_context(current))
                store.upsert(
                    _touch(
                        current,
                        status="running",
                        stage="import",
                        progress=5,
                        progress_label="Running full pipeline",
                        started_at=current.started_at or datetime.now().isoformat(timespec="seconds"),
                        error_detail=None,
                    )
                )

                def progress_update(progress: int, stage: str, label: str) -> None:
                    latest = store.get(current.id) or current
                    _append_logs(latest, f"[{stage}] {label} ({progress}%)")
                    store.upsert(
                        _touch(
                            latest,
                            status="running",
                            stage=stage,
                            progress=progress,
                            progress_label=label,
                        )
                    )

                latest = store.get(current.id) or current
                current = run_full_pipeline(latest, progress_callback=progress_update, cleanup_intermediate=True)
                _append_logs(current, "task complete: full", *(f"output: {path}" for path in current.outputs[-12:]))
                store.upsert(
                    _touch(
                        current,
                        status="ready",
                        stage="export",
                        progress=100,
                        progress_label="Completed",
                    )
                )
                return

            if step not in transitions:
                _append_logs(current, f"step not implemented: {step}")
                store.upsert(_touch(current, status="failed", progress_label=f"Unsupported step: {step}"))
                return

            progress, stage, label = transitions[step]
            _append_logs(current, f"task start: {stage}", f"[{stage}] {label}", *summarize_job_context(current))
            store.upsert(
                _touch(
                    current,
                    status="running",
                    stage=stage,
                    progress=progress,
                    progress_label=label,
                    started_at=current.started_at or datetime.now().isoformat(timespec="seconds"),
                    error_detail=None,
                )
            )

            latest = store.get(current.id) or current
            current = runners[step](latest)
            _append_logs(current, f"task complete: {stage}", *(f"output: {path}" for path in current.outputs[-12:]))
            store.upsert(
                _touch(
                    current,
                    status="ready",
                    stage=step,
                    progress=100,
                    progress_label=f"{label} complete",
                    error_detail=None,
                )
            )
        except Exception as exc:
            current = store.get(job.id) or current
            detail = _format_exception(exc)
            current.notes = [str(exc)]
            _append_logs(current, f"task failed: {step}", detail.strip())
            store.upsert(
                _touch(
                    current,
                    status="failed",
                    progress_label="Execution failed",
                    error_detail=detail,
                )
            )

    threading.Thread(target=worker, daemon=True).start()


def create_handler(
    repo_root: Path,
    source_root: Path,
    static_root: Path | None = None,
    default_output_root: Path | None = None,
):
    state = {
        "source_root": str(source_root),
        "default_output_root": str(default_output_root or (repo_root / ".work" / "outputs")),
    }
    store = JobStore(repo_root / ".work" / "appdata")
    frontend_dist = static_root if static_root is not None else (repo_root / "frontend" / "dist")

    class ApiHandler(BaseHTTPRequestHandler):
        def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _send_bytes(self, body: bytes, content_type: str, status: int = HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_file(self, file_path: Path) -> None:
            if not file_path.exists() or not file_path.is_file():
                self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
                return
            content_type, _ = mimetypes.guess_type(str(file_path))
            self._send_bytes(file_path.read_bytes(), content_type or "application/octet-stream")

        def _serve_frontend(self, request_path: str) -> None:
            if not frontend_dist.exists():
                self._send_json({"error": "frontend dist not found"}, status=HTTPStatus.NOT_FOUND)
                return

            clean_path = request_path.lstrip("/") or "index.html"
            target = (frontend_dist / clean_path).resolve()
            if frontend_dist.resolve() not in target.parents and target != frontend_dist.resolve():
                self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
                return

            if target.exists() and target.is_file():
                self._serve_file(target)
                return

            self._serve_file(frontend_dist / "index.html")

        def _pick_directory(self, payload: dict) -> None:
            try:
                import tkinter as tk
                from tkinter import filedialog

                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                selected = filedialog.askdirectory(
                    initialdir=str(payload.get("current_path") or state["default_output_root"]),
                    title=payload.get("title") or "Select directory",
                )
                root.destroy()
                self._send_json({"path": selected or ""})
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        def _save_uploaded_file(self) -> None:
            source_dir = Path(state["source_root"])
            source_dir.mkdir(parents=True, exist_ok=True)
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                },
            )
            file_item = form["file"] if "file" in form else None
            if file_item is None or not getattr(file_item, "filename", ""):
                self._send_json({"error": "missing file"}, status=HTTPStatus.BAD_REQUEST)
                return

            filename = _safe_uploaded_name(file_item.filename)
            target = source_dir / filename
            stem = target.stem
            suffix = target.suffix
            index = 1
            while target.exists():
                target = source_dir / f"{stem}_{index}{suffix}"
                index += 1

            with target.open("wb") as handle:
                handle.write(file_item.file.read())
            self._send_json({"ok": True, "file_name": target.name, "path": str(target)}, status=HTTPStatus.CREATED)

        def _save_uploaded_images(self) -> None:
            source_dir = Path(state["source_root"])
            source_dir.mkdir(parents=True, exist_ok=True)
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                },
            )
            items = form["files"] if "files" in form else None
            if items is None:
                self._send_json({"error": "missing files"}, status=HTTPStatus.BAD_REQUEST)
                return
            if not isinstance(items, list):
                items = [items]

            target_name = _safe_uploaded_name(form.getfirst("target_name", "") or "图片素材")
            target_root = source_dir / Path(target_name).stem
            index = 1
            while target_root.exists():
                target_root = source_dir / f"{Path(target_name).stem}_{index}"
                index += 1
            target_root.mkdir(parents=True, exist_ok=True)

            saved: list[str] = []
            for item in items:
                filename = getattr(item, "filename", "") or ""
                if not filename:
                    continue
                relative_name = _safe_relative_name(filename)
                destination = target_root / relative_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("wb") as handle:
                    handle.write(item.file.read())
                saved.append(str(destination))

            if not saved:
                self._send_json({"error": "missing files"}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json(
                {
                    "ok": True,
                    "folder_name": target_root.name,
                    "path": str(target_root),
                    "count": len(saved),
                },
                status=HTTPStatus.CREATED,
            )

        def _import_source_directory(self, payload: dict) -> None:
            selected = Path(payload.get("path") or "")
            if not selected.exists() or not selected.is_dir():
                self._send_json({"error": "directory not found"}, status=HTTPStatus.NOT_FOUND)
                return

            source_dir = Path(state["source_root"])
            source_dir.mkdir(parents=True, exist_ok=True)

            target = source_dir / selected.name
            index = 1
            while target.exists():
                target = source_dir / f"{selected.name}_{index}"
                index += 1

            shutil.copytree(selected, target)
            self._send_json(
                {
                    "ok": True,
                    "folder_name": target.name,
                    "path": str(target),
                },
                status=HTTPStatus.CREATED,
            )

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/dashboard":
                payload = build_dashboard_data(
                    repo_root,
                    Path(state["source_root"]),
                    default_output_root=Path(state["default_output_root"]),
                ).to_dict()
                self._send_json(payload)
                return
            if parsed.path == "/api/health":
                self._send_json({"ok": True})
                return

            if parsed.path == "/api/models":
                from .enhancers.registry import list_enhancers
                from .enhancers.realesrgan_anime_enhancer import RealESRGANAnimeEnhancer
                raw = list_enhancers()
                # 附加 hint 字段：RE 库已装但模型文件缺失时，告知用户放置路径
                models = []
                for m in raw:
                    entry = dict(m)
                    if m["name"] == "realesrgan-anime" and not m["available"]:
                        try:
                            entry["hint"] = RealESRGANAnimeEnhancer().model_file_hint()
                        except Exception:
                            pass
                    models.append(entry)
                self._send_json({"models": models})
                return

            self._serve_frontend(parsed.path)

        def do_POST(self) -> None:
            try:
                parsed = urlparse(self.path)

                if parsed.path == "/api/import-file":
                    self._save_uploaded_file()
                    return

                if parsed.path == "/api/import-images":
                    self._save_uploaded_images()
                    return

                payload = _read_json_body(self)

                if parsed.path == "/api/config":
                    source_value = payload.get("source_root")
                    has_output_value = "default_output_root" in payload
                    output_value = payload.get("default_output_root")
                    if source_value:
                        state["source_root"] = str(Path(source_value))
                    if has_output_value:
                        state["default_output_root"] = (
                            str(Path(output_value))
                            if output_value
                            else str(repo_root / ".work" / "outputs")
                        )
                    self._send_json(
                        {
                            "source_root": state["source_root"],
                            "default_output_root": state["default_output_root"],
                        }
                    )
                    return

                if parsed.path == "/api/jobs":
                    current_source_root = Path(state["source_root"])
                    source_name = payload.get("source_name")
                    source_path = (current_source_root / source_name) if source_name else Path(payload["source_path"])
                    output_dir = Path(payload.get("output_dir") or state["default_output_root"])
                    job = store.create(
                        name=payload.get("name") or source_path.stem,
                        source_name=source_name or source_path.name,
                        source_path=str(source_path),
                        workspace_root=str(repo_root / ".work" / "app_jobs"),
                        output_dir=str(output_dir),
                        output_formats=list(payload.get("output_formats") or ["cbz"]),
                        target_device=payload.get("target_device") or "android-tablet",
                        keep_original_pages=bool(payload.get("keep_original_pages", True)),
                        keep_enhanced_pages=bool(payload.get("keep_enhanced_pages", True)),
                        strategy=str(payload.get("strategy") or "quality_auto"),
                        enhancer=str(payload.get("enhancer") or ""),
                        enhance_scale=float(payload.get("enhance_scale") or 1.5),
                        waifu2x_noise=int(payload.get("waifu2x_noise") if payload.get("waifu2x_noise") is not None else 1),
                        waifu2x_tta=bool(payload.get("waifu2x_tta", False)),
                        waifu2x_model=str(payload.get("waifu2x_model") or "models-cunet"),
                        pdf_mode=str(payload.get("pdf_mode") or "auto"),
                        pdf_quality_mode=str(payload.get("pdf_quality_mode") or "fast_auto"),
                        pdf_image_format=str(payload.get("pdf_image_format") or "jpg"),
                        pdf_render_dpi=int(payload.get("pdf_render_dpi") or 300),
                    )
                    self._send_json({"job": job_to_payload(job)}, status=HTTPStatus.CREATED)
                    return

                if parsed.path == "/api/merge-sources":
                    source_names = list(payload.get("source_names") or [])
                    if len(source_names) < 2:
                        self._send_json({"error": "select at least two sources"}, status=HTTPStatus.BAD_REQUEST)
                        return
                    source_paths = [(Path(state["source_root"]) / name) for name in source_names]
                    missing = [str(path) for path in source_paths if not path.exists()]
                    if missing:
                        self._send_json({"error": "source not found", "missing": missing}, status=HTTPStatus.NOT_FOUND)
                        return
                    output_dir = Path(payload.get("output_dir") or state["default_output_root"])
                    manifest = merge_sources(
                        source_paths,
                        output_dir,
                        list(payload.get("output_formats") or ["cbz"]),
                        target_name=payload.get("merge_name") or None,
                    )
                    self._send_json({"merge": manifest}, status=HTTPStatus.CREATED)
                    return

                if parsed.path == "/api/pick-directory":
                    self._pick_directory(payload)
                    return

                if parsed.path == "/api/import-source-directory":
                    self._import_source_directory(payload)
                    return

                if parsed.path == "/api/open-path":
                    target = Path(payload["path"])
                    if not target.exists():
                        self._send_json({"error": "path not found"}, status=HTTPStatus.NOT_FOUND)
                        return
                    os.startfile(str(target))
                    self._send_json({"ok": True})
                    return

                if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/run-full"):
                    job_id = parsed.path.split("/")[3]
                    job = store.get(job_id)
                    if not job:
                        self._send_json({"error": "job not found"}, status=HTTPStatus.NOT_FOUND)
                        return
                    _run_in_background(store, job, "full")
                    self._send_json({"job": job_to_payload(store.get(job_id) or job)}, status=HTTPStatus.ACCEPTED)
                    return

                if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/run-step"):
                    job_id = parsed.path.split("/")[3]
                    job = store.get(job_id)
                    if not job:
                        self._send_json({"error": "job not found"}, status=HTTPStatus.NOT_FOUND)
                        return
                    step = payload.get("step")
                    if step not in {"split", "enhance_module", "export_module", "import", "analyze", "enhance", "optimize", "package", "export"}:
                        self._send_json({"error": f"step not implemented: {step}"}, status=HTTPStatus.NOT_IMPLEMENTED)
                        return
                    _run_in_background(store, job, step)
                    self._send_json({"job": job_to_payload(store.get(job_id) or job)}, status=HTTPStatus.ACCEPTED)
                    return

                self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self._send_json({"error": str(exc), "detail": _format_exception(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_DELETE(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/jobs/"):
                job_id = parsed.path.split("/")[3]
                if not store.delete(job_id):
                    self._send_json({"error": "job not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"ok": True})
                return
            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args) -> None:
            return

    return ApiHandler


def main() -> int:
    parser = argparse.ArgumentParser(description="Local API for manga enhancement frontend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    args = parser.parse_args()

    handler = create_handler(
        args.repo_root,
        args.source_root,
        static_root=args.repo_root / "frontend" / "dist",
        default_output_root=args.repo_root / ".work" / "outputs",
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"API listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
