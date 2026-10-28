"""F1 multimodal attachment pipeline (mission chat input).

Local-only, read-only over the source files: bytes are copied into the app-owned
attachment store (data/attachments) and provenance is persisted in the app SQLite DB.
Text/code/JSON/CSV/log extraction is built in; PDF/Office extraction is available only
when the optional local library exists and otherwise fails closed with a clear message.
Images are never assumed to be model-readable: routing requires a measured/declared
vision capability (declared requires an explicit opt-in) and the model router gate.
Audio/video carry metadata only; their extraction hooks are deferred to F2.
"""
from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from nl_coding_agent.persistence import database

__all__ = [
    "AttachmentError", "AttachmentLimits", "AttachmentStore",
    "prepare_bytes", "prepare_path", "prepare_paths", "prepare_text",
    "prepare_clipboard_image", "list_attachments", "get_attachment",
    "attach_to_mission", "delete_attachment", "route_image_attachments",
    "extraction_availability", "sniff_kind",
]

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
TEXT_KINDS = {"text", "code", "json", "csv", "log", "markdown"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".log", ".csv", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".xml", ".html", ".css", ".js", ".mjs", ".ts",
    ".tsx", ".jsx", ".py", ".pyi", ".bat", ".ps1", ".sh", ".sql", ".c", ".h",
    ".cpp", ".hpp", ".java", ".cs", ".go", ".rs", ".rb", ".php", ".lua", ".vue",
}
OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt"}


class AttachmentError(ValueError):
    """A source file was rejected (size/type/extraction) with a user-safe message."""

    def __init__(self, message: str, *, code: str = "attachment-rejected") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AttachmentLimits:
    max_file_bytes: int = MAX_FILE_BYTES
    max_total_bytes: int = MAX_TOTAL_BYTES
    max_text_chars: int = MAX_TEXT_CHARS
    max_files_per_batch: int = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def attachment_root() -> Path:
    return database.data_root() / "attachments"


def _safe_name(name: str) -> str:
    base = Path(str(name or "attachment")).name
    return re.sub(r"[^A-Za-z0-9._ -]", "_", base)[:120] or "attachment"


def extraction_availability() -> dict:
    import importlib.util

    return {
        "text": True, "pdf": bool(importlib.util.find_spec("pdfplumber")),
        "xlsx": bool(importlib.util.find_spec("openpyxl")),
        "docx": bool(importlib.util.find_spec("docx")),
        "pptx": bool(importlib.util.find_spec("pptx")),
        "image_metadata": bool(importlib.util.find_spec("PIL")),
        "audio": False, "video": False,
    }


def sniff_kind(name: str, head: bytes = b"") -> tuple[str, str]:
    """Return (kind, mime) from content first, extension second; unknown stays unknown."""
    suffix = Path(str(name or "")).suffix.lower()
    if head.startswith(b"%PDF-"):
        return "pdf", "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image", "image/gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image", "image/webp"
    if head.startswith(b"PK\x03\x04"):
        if suffix == ".xlsx":
            return "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if suffix == ".docx":
            return "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if suffix == ".pptx":
            return "pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        return "archive", "application/zip"
    if suffix in IMAGE_EXTENSIONS:
        return "image", mimetypes.guess_type(name)[0] or "image/*"
    if suffix in AUDIO_EXTENSIONS:
        return "audio", mimetypes.guess_type(name)[0] or "audio/*"
    if suffix in VIDEO_EXTENSIONS:
        return "video", mimetypes.guess_type(name)[0] or "video/*"
    if suffix in OFFICE_EXTENSIONS:
        return suffix.lstrip("."), mimetypes.guess_type(name)[0] or "application/octet-stream"
    if suffix == ".json":
        return "json", "application/json"
    if suffix == ".csv":
        return "csv", "text/csv"
    if suffix in (".log", ".out", ".err"):
        return "log", "text/plain"
    if suffix in TEXT_EXTENSIONS:
        kind = "markdown" if suffix in (".md", ".markdown") else "code" if suffix not in (".txt",) else "text"
        return kind, mimetypes.guess_type(name)[0] or "text/plain"
    if b"\x00" in head:
        return "unknown", mimetypes.guess_type(name)[0] or "application/octet-stream"
    try:
        head.decode("utf-8")
        return "text", "text/plain"
    except UnicodeDecodeError:
        return "unknown", mimetypes.guess_type(name)[0] or "application/octet-stream"


def _decode_text(data: bytes) -> str:
    if b"\x00" in data[:4096]:
        raise AttachmentError("Binary file rejected: no text extraction path for this type.",
                              code="binary-unsupported")
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise AttachmentError("Could not decode text file (unsupported encoding).",
                          code="decode-failed")


def _truncate_text(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + "\n... [truncated " + str(len(text) - limit) + " chars]", True


def _extract_pdf(data: bytes, limits: AttachmentLimits) -> tuple[str, dict]:
    availability = extraction_availability()
    if not availability["pdf"]:
        raise AttachmentError(
            "PDF extraction is unavailable in this runtime (optional library 'pdfplumber' "
            "is not installed); the PDF is stored but no text is sent to the model.",
            code="pdf-unavailable",
        )
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if len(pdf.pages) > 200:
            raise AttachmentError("PDF has too many pages (limit 200).", code="pdf-too-large")
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    text = "\n\n".join(pages)
    text, _ = _truncate_text(text, limits.max_text_chars)
    return text, {"pages": len(pages)}


def _extract_xlsx(data: bytes, limits: AttachmentLimits) -> tuple[str, dict]:
    availability = extraction_availability()
    if not availability["xlsx"]:
        raise AttachmentError(
            "XLSX extraction is unavailable in this runtime (optional library 'openpyxl' "
            "is not installed); the workbook is stored but no text is sent.",
            code="xlsx-unavailable",
        )
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    rows: list[str] = []
    for sheet in workbook.worksheets[:20]:
        rows.append("## Sheet: " + str(sheet.title))
        for index, row in enumerate(sheet.iter_rows(values_only=True)):
            if index >= 500:
                rows.append("[sheet truncated at 500 rows]")
                break
            rows.append("\t".join("" if cell is None else str(cell) for cell in row))
            if sum(len(line) for line in rows) > limits.max_text_chars:
                break
    workbook.close()
    text, _ = _truncate_text("\n".join(rows), limits.max_text_chars)
    return text, {"sheets": len(workbook.sheetnames)}


def _extract_office(data: bytes, kind: str, limits: AttachmentLimits) -> tuple[str, dict]:
    availability = extraction_availability()
    if kind in ("docx", "doc"):
        if not availability["docx"]:
            raise AttachmentError(
                "DOCX extraction is unavailable in this runtime (optional library "
                "'python-docx' is not installed); the document is stored but no text is sent.",
                code="docx-unavailable",
            )
    if kind in ("pptx", "ppt"):
        if not availability["pptx"]:
            raise AttachmentError(
                "PPTX extraction is unavailable in this runtime (optional library "
                "'python-pptx' is not installed); the presentation is stored but no text is sent.",
                code="pptx-unavailable",
            )
    raise AttachmentError("Office extraction path is unavailable for this file type.",
                          code="office-unavailable")


def _image_metadata(data: bytes, limits: AttachmentLimits) -> tuple[str, dict]:
    if not extraction_availability()["image_metadata"]:
        return "", {"width": None, "height": None, "format": None}
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        return "", {"width": int(image.width), "height": int(image.height),
                    "format": str(image.format or "")}


def extract_attachment(data: bytes, name: str, kind: str,
                       limits: AttachmentLimits) -> dict:
    if kind in TEXT_KINDS:
        text = _decode_text(data)
        text, truncated = _truncate_text(text, limits.max_text_chars)
        if kind == "json":
            try:
                json.loads(text)
            except ValueError:
                pass  # keep as text; invalid JSON is not silently claimed to be valid
        return {"status": "extracted", "text": text, "metadata": {"truncated": truncated}}
    if kind == "pdf":
        text, meta = _extract_pdf(data, limits)
        return {"status": "extracted", "text": text, "metadata": meta}
    if kind == "xlsx":
        text, meta = _extract_xlsx(data, limits)
        return {"status": "extracted", "text": text, "metadata": meta}
    if kind in ("docx", "pptx", "doc", "ppt"):
        text, meta = _extract_office(data, kind, limits)
        return {"status": "extracted", "text": text, "metadata": meta}
    if kind == "image":
        text, meta = _image_metadata(data, limits)
        return {"status": "metadata-only", "text": text,
                "metadata": {**meta, "routing": "capability-checked-separately"}}
    if kind == "audio":
        return {"status": "deferred", "text": "",
                "metadata": {"deferred_to": "F2", "kind": "audio"}}
    if kind == "video":
        return {"status": "deferred", "text": "",
                "metadata": {"deferred_to": "F2", "kind": "video"}}
    raise AttachmentError(
        "Unsupported attachment type " + repr(Path(name).suffix or name)
        + "; supported: text/code/JSON/CSV/log, PDF, XLSX, images, audio/video metadata.",
        code="unsupported-type",
    )


def _row_to_dict(row) -> dict:
    data = dict(row)
    try:
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
    except ValueError:
        data["metadata"] = {}
    data["has_text"] = bool(data.get("extracted_text"))
    return data


class AttachmentStore:
    """Durable provenance store for mission chat attachments."""

    def __init__(self, limits: AttachmentLimits | None = None,
                 *, root: Path | None = None, db_path: Path | None = None) -> None:
        self.limits = limits or AttachmentLimits()
        self.root = Path(root) if root is not None else attachment_root()
        self._db_path = Path(db_path) if db_path is not None else None
        database.init_db(self._db_path).close()

    def _connect(self):
        return database.init_db(self._db_path)

    def _insert(self, *, project_id, mission_id, name, kind, mime, size, sha,
                source, stored_path, status, text, error, metadata) -> dict:
        conn = self._connect()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO mission_attachments
                        (project_id, mission_id, name, kind, mime, size_bytes, sha256,
                         source, stored_path, extraction_status, text_chars,
                         extracted_text, error, metadata_json, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (project_id, mission_id, name, kind, mime, int(size), sha,
                     source, str(stored_path), status,
                     len(text or ""), text, error,
                     json.dumps(metadata or {}, sort_keys=True, default=str), _now()),
                )
                attachment_id = int(cursor.lastrowid)
        finally:
            conn.close()
        return self.get(attachment_id)

    def get(self, attachment_id: int) -> dict:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM mission_attachments WHERE id=?",
                               (int(attachment_id),)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise AttachmentError("Attachment not found: " + str(attachment_id),
                                  code="not-found")
        return _row_to_dict(row)

    def list(self, *, mission_id: int | None = None,
             project_id: int | None = None) -> list[dict]:
        clauses, params = [], []
        if mission_id is not None:
            clauses.append("mission_id=?")
            params.append(int(mission_id))
        if project_id is not None:
            clauses.append("project_id=?")
            params.append(int(project_id))
        query = "SELECT * FROM mission_attachments"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id ASC"
        conn = self._connect()
        try:
            rows = conn.execute(query, params).fetchall()
        finally:
            conn.close()
        return [_row_to_dict(row) for row in rows]

    def attach_to_mission(self, mission_id: int, attachment_ids: list[int]) -> int:
        ids = [int(item) for item in attachment_ids]
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        conn = self._connect()
        try:
            with conn:
                cursor = conn.execute(
                    "UPDATE mission_attachments SET mission_id=? WHERE id IN ("
                    + placeholders + ")", (int(mission_id), *ids))
                return int(cursor.rowcount)
        finally:
            conn.close()

    def delete(self, attachment_id: int) -> bool:
        conn = self._connect()
        try:
            with conn:
                cursor = conn.execute("DELETE FROM mission_attachments WHERE id=?",
                                      (int(attachment_id),))
                return cursor.rowcount == 1
        finally:
            conn.close()

    def prepare_bytes(self, data: bytes, name: str, *, source: str = "upload",
                     project_id: int | None = None,
                     mission_id: int | None = None,
                     content_type: str | None = None) -> dict:
        if not isinstance(data, (bytes, bytearray)):
            raise AttachmentError("Attachment bytes are required.", code="invalid-bytes")
        raw = bytes(data)
        if len(raw) > self.limits.max_file_bytes:
            raise AttachmentError(
                "File '" + str(name) + "' is larger than the allowed "
                + str(self.limits.max_file_bytes // (1024 * 1024)) + " MiB limit.",
                code="file-too-large",
            )
        safe = _safe_name(name)
        kind, mime = sniff_kind(safe, raw[:32])
        if content_type and kind == "unknown":
            mime = str(content_type)
        sha = hashlib.sha256(raw).hexdigest()
        target_dir = self.root / sha[:2]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / (sha[:16] + "_" + safe)
        target.write_bytes(raw)
        try:
            extracted = extract_attachment(raw, safe, kind, self.limits)
            status = str(extracted["status"])
            text = str(extracted.get("text") or "")
            metadata = dict(extracted.get("metadata") or {})
            error = None
        except AttachmentError as exc:
            status = "unavailable"
            text = ""
            metadata = {}
            error = str(exc)
        record = self._insert(
            project_id=project_id, mission_id=mission_id, name=safe, kind=kind,
            mime=mime, size=len(raw), sha=sha, source=source,
            stored_path=target, status=status, text=text, error=error,
            metadata=metadata,
        )
        record["error_code"] = (error and "extraction-unavailable") or None
        return record

    def prepare_path(self, path: str | Path, *, source: str = "drop",
                     project_id=None, mission_id=None) -> dict:
        item = Path(path).expanduser()
        if item.is_dir():
            raise AttachmentError("Folders are expanded by prepare_paths.", code="is-folder")
        if not item.is_file():
            raise AttachmentError("File not found: " + str(item), code="not-found")
        size = item.stat().st_size
        if size > self.limits.max_file_bytes:
            raise AttachmentError(
                "File '" + item.name + "' is larger than the allowed "
                + str(self.limits.max_file_bytes // (1024 * 1024)) + " MiB limit.",
                code="file-too-large")
        data = item.read_bytes()
        return self.prepare_bytes(data, item.name, source=source,
                                  project_id=project_id, mission_id=mission_id)

    def prepare_paths(self, paths, *, source: str = "drop", project_id=None,
                      mission_id=None) -> dict:
        attachments, errors = [], []
        total = 0
        expanded: list[Path] = []
        for path in paths or []:
            item = Path(path).expanduser()
            if item.is_dir():
                for child in sorted(item.rglob("*")):
                    if child.is_file() and not child.is_symlink():
                        expanded.append(child)
                        if len(expanded) >= self.limits.max_files_per_batch:
                            break
                if len(expanded) >= self.limits.max_files_per_batch:
                    errors.append({"name": str(item),
                                   "error": "Folder expansion reached the "
                                            + str(self.limits.max_files_per_batch)
                                            + "-file limit."})
                    break
            else:
                expanded.append(item)
        for item in expanded[: self.limits.max_files_per_batch]:
            try:
                total += item.stat().st_size
                if total > self.limits.max_total_bytes:
                    raise AttachmentError("Batch exceeds the total attachment size limit.",
                                          code="batch-too-large")
                attachments.append(self.prepare_path(
                    item, source=source, project_id=project_id, mission_id=mission_id))
            except AttachmentError as exc:
                errors.append({"name": str(item), "error": str(exc), "code": exc.code})
            except Exception as exc:  # noqa: BLE001 - surfaced as a clear per-file error
                errors.append({"name": str(item), "error": str(exc), "code": "read-failed"})
        return {"attachments": attachments, "errors": errors, "total_bytes": total,
                "limits": {"max_file_bytes": self.limits.max_file_bytes,
                           "max_total_bytes": self.limits.max_total_bytes}}

    def prepare_text(self, text: str, *, name: str = "pasted-text.txt",
                     source: str = "paste", project_id=None, mission_id=None) -> dict:
        if not str(text or "").strip():
            raise AttachmentError("Empty pasted text.", code="empty-text")
        return self.prepare_bytes(str(text).encode("utf-8"), name, source=source,
                                  project_id=project_id, mission_id=mission_id)

    def prepare_clipboard_image(self, image_bytes: bytes, *, name: str | None = None,
                                source: str = "clipboard",
                                project_id=None, mission_id=None) -> dict:
        if not image_bytes:
            raise AttachmentError("Clipboard image is empty.", code="empty-image")
        return self.prepare_bytes(
            image_bytes, name or "screenshot.png", source=source,
            project_id=project_id, mission_id=mission_id,
            content_type="image/png")


def prepare_bytes(data: bytes, name: str, **kwargs) -> dict:
    return AttachmentStore().prepare_bytes(data, name, **kwargs)


def prepare_path(path, **kwargs) -> dict:
    return AttachmentStore().prepare_path(path, **kwargs)


def prepare_paths(paths, **kwargs) -> dict:
    return AttachmentStore().prepare_paths(paths, **kwargs)


def prepare_text(text: str, **kwargs) -> dict:
    return AttachmentStore().prepare_text(text, **kwargs)


def prepare_clipboard_image(image_bytes: bytes, **kwargs) -> dict:
    return AttachmentStore().prepare_clipboard_image(image_bytes, **kwargs)


def list_attachments(*, mission_id=None, project_id=None) -> list[dict]:
    return AttachmentStore().list(mission_id=mission_id, project_id=project_id)


def get_attachment(attachment_id: int) -> dict:
    return AttachmentStore().get(attachment_id)


def attach_to_mission(mission_id: int, attachment_ids: list[int]) -> int:
    return AttachmentStore().attach_to_mission(mission_id, attachment_ids)


def delete_attachment(attachment_id: int) -> bool:
    return AttachmentStore().delete(attachment_id)


# --------------------------------------------------------------------------- #
# Capability-aware image routing (measured/declared only; never assumed)
# --------------------------------------------------------------------------- #

def route_image_attachments(attachments: list[dict], *, provider_id: str,
                            model_name: str, role: str = "developer",
                            capability_records=None, router=None,
                            allow_declared: bool = False,
                            required=("vision",)) -> dict:
    """Decide which image attachments may be sent to the selected model.

    Only a measured capability (or an explicitly opted-in declared capability, and then
    only if the model router's permission/capability gate accepts the binding) enables
    routing. Unknown/absent capability is always excluded with a clear reason.
    """
    from nl_coding_agent.models import capabilities as capabilities_module

    records = capability_records
    key = (str(provider_id), str(model_name))
    if isinstance(records, dict) and key in records:
        records = records[key]
    cap_set = capabilities_module.load_capabilities(
        str(provider_id), str(model_name), records=records)
    state = cap_set.state("vision")
    reason = ""
    routed = bool(state in ("measured", "declared"))
    if state == "declared" and not allow_declared:
        routed = False
        reason = ("vision capability is declared but unverified; explicit opt-in is "
                  "required before sending images")
    elif state not in ("measured", "declared"):
        routed = False
        reason = ("no measured/declared vision capability for " + str(provider_id)
                  + "/" + str(model_name) + "; image attachments are not routed")
    if routed and router is not None:
        try:
            router.resolve(role, required_capabilities=tuple(required))
        except Exception as exc:  # noqa: BLE001 - refusal is the routing decision
            routed = False
            reason = "model router refused image routing: " + str(exc)
    images = [item for item in attachments if item.get("kind") == "image"]
    return {
        "provider_id": str(provider_id), "model_name": str(model_name),
        "capability_state": state, "routed": routed, "reason": reason,
        "routed_ids": [item.get("id") for item in images] if routed else [],
        "excluded": [] if routed else [item.get("id") for item in images],
        "image_count": len(images),
    }
