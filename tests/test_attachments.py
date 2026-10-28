"""F1 attachments: local extraction, provenance across restart, capability-gated images."""
from __future__ import annotations

import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from nl_coding_agent.app import attachments as att
from nl_coding_agent.persistence import database


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    database.init_db().close()


def test_text_code_json_csv_log_extraction_and_persistence(tmp_path):
    store = att.AttachmentStore()
    files = {
        "notes.txt": "hello world\n",
        "module.py": "def f():\n    return 1\n",
        "data.json": json.dumps({"ok": True}),
        "rows.csv": "a,b\n1,2\n",
        "run.log": "2026 INFO started\n",
        "README.md": "# Title\n",
    }
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    result = store.prepare_paths([tmp_path / name for name in files], project_id=1)
    assert result["errors"] == []
    assert len(result["attachments"]) == len(files)
    kinds = {item["name"]: item["kind"] for item in result["attachments"]}
    assert kinds["module.py"] == "code"
    assert kinds["data.json"] == "json"
    assert kinds["rows.csv"] == "csv"
    assert kinds["run.log"] == "log"
    assert kinds["README.md"] == "markdown"
    for item in result["attachments"]:
        assert item["extraction_status"] == "extracted"
        assert item["has_text"] is True
        assert Path(item["stored_path"]).is_file()
    # provenance survives a new store instance (restart)
    reopened = att.AttachmentStore()
    listed = reopened.list(project_id=1)
    assert len(listed) == len(files)
    assert reopened.get(listed[0]["id"])["name"] == listed[0]["name"]


def test_xlsx_extraction_when_openpyxl_available(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "book.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["A1"] = "name"
    sheet["B1"] = "value"
    sheet["A2"] = "alpha"
    sheet["B2"] = 42
    workbook.save(path)
    item = att.AttachmentStore().prepare_path(path, project_id=2)
    assert item["kind"] == "xlsx"
    assert item["extraction_status"] == "extracted"
    assert "alpha" in (item["extracted_text"] or "")


def test_pdf_and_office_fail_closed_with_clear_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(att, "extraction_availability", lambda: {
        "text": True, "pdf": False, "xlsx": False, "docx": False, "pptx": False,
        "image_metadata": True, "audio": False, "video": False})
    store = att.AttachmentStore()
    pdf = store.prepare_bytes(b"%PDF-1.4 fake", "doc.pdf")
    assert pdf["kind"] == "pdf" and pdf["extraction_status"] == "unavailable"
    assert "pdfplumber" in (pdf["error"] or "")
    docx = store.prepare_bytes(b"PK\x03\x04fake", "letter.docx")
    assert docx["kind"] == "docx" and "python-docx" in (docx["error"] or "")
    pptx = store.prepare_bytes(b"PK\x03\x04fake", "slides.pptx")
    assert pptx["kind"] == "pptx" and "python-pptx" in (pptx["error"] or "")


def test_size_limits_and_unsupported_types(tmp_path):
    store = att.AttachmentStore(limits=att.AttachmentLimits(max_file_bytes=10))
    with pytest.raises(att.AttachmentError) as caught:
        store.prepare_bytes(b"x" * 20, "big.txt")
    assert caught.value.code == "file-too-large"
    binary = store.prepare_bytes(bytes([0, 1, 2, 3, 4, 5]), "blob.bin")
    assert binary["extraction_status"] == "unavailable"
    assert "Unsupported attachment type" in (binary["error"] or "")


def test_folder_expansion_paste_text_clipboard_image_and_audio_video(tmp_path):
    store = att.AttachmentStore()
    folder = tmp_path / "bundle"
    (folder / "nested").mkdir(parents=True)
    (folder / "a.txt").write_text("a", encoding="utf-8")
    (folder / "nested" / "b.py").write_text("b = 1\n", encoding="utf-8")
    batch = store.prepare_paths([folder], project_id=3)
    assert {item["name"] for item in batch["attachments"]} == {"a.txt", "b.py"}
    text = store.prepare_text("pasted mission context", project_id=3)
    assert text["kind"] == "text" and text["source"] == "paste"
    image = store.prepare_clipboard_image(
        bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000100050505c9d6a3f00000000049454e44ae426082"),
        project_id=3)
    assert image["kind"] == "image" and image["extraction_status"] == "metadata-only"
    audio = store.prepare_bytes(b"ID3fake", "sound.mp3", project_id=3)
    assert audio["kind"] == "audio"
    assert audio["metadata"]["deferred_to"] == "F2"
    video = store.prepare_bytes(b"\x00\x00\x00\x18ftypmp42", "clip.mp4", project_id=3)
    assert video["kind"] == "video"
    assert video["metadata"]["deferred_to"] == "F2"


def test_attach_delete_and_no_network_for_local_preparation(tmp_path, monkeypatch):
    store = att.AttachmentStore()
    item = store.prepare_text("line one\nline two", project_id=4)
    assert store.attach_to_mission(77, [item["id"]]) == 1
    assert store.get(item["id"])["mission_id"] == 77
    assert len(store.list(mission_id=77)) == 1
    assert store.delete(item["id"]) is True
    with pytest.raises(att.AttachmentError):
        store.get(item["id"])

    def _no_network(*args, **kwargs):
        raise AssertionError("attachment preparation must not use the network")
    monkeypatch.setattr(socket, "socket", _no_network)
    assert store.prepare_text("local only", project_id=4)["kind"] == "text"


def _caps(state):
    from nl_coding_agent.models.capabilities import CapabilityRecord
    record = CapabilityRecord("ollama", "vision-model", "vision", state)
    return {("ollama", "vision-model"): {"vision": record}}


def test_image_routing_requires_measured_or_explicitly_declared_capability():
    images = [{"id": 1, "kind": "image", "name": "shot.png"}]
    unknown = att.route_image_attachments(
        images, provider_id="ollama", model_name="vision-model",
        capability_records={})
    assert unknown["routed"] is False
    assert unknown["excluded"] == [1]
    assert "no measured/declared vision" in unknown["reason"]

    measured = att.route_image_attachments(
        images, provider_id="ollama", model_name="vision-model",
        capability_records=_caps("measured"))
    assert measured["routed"] is True and measured["routed_ids"] == [1]

    declared = att.route_image_attachments(
        images, provider_id="ollama", model_name="vision-model",
        capability_records=_caps("declared"))
    assert declared["routed"] is False
    declared_optin = att.route_image_attachments(
        images, provider_id="ollama", model_name="vision-model",
        capability_records=_caps("declared"), allow_declared=True)
    assert declared_optin["routed"] is True
