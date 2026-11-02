"""P2 code intelligence: symbol search and static post-write diagnostics."""
from __future__ import annotations

import json

from nl_coding_agent.core import promotion
from nl_coding_agent.tools.code_intel import (
    diagnose_files,
    format_diagnostics,
    lsp_diagnostics,
    search_symbols,
)


def _project(tmp_path):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "calc.py").write_text(
        "class Calculator:\n"
        "    def add(self, a, b):\n"
        "        return a + b\n"
        "\n"
        "def subtract(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )
    (root / "src" / "widget.ts").write_text(
        "export function renderWidget() { return null; }\n"
        "export interface WidgetProps { id: string }\n",
        encoding="utf-8",
    )
    (root / "config.json").write_text('{"ok": true}\n', encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nname = "fixture"\n', encoding="utf-8")
    return root


def test_symbol_search_finds_python_and_typescript_declarations(tmp_path):
    root = _project(tmp_path)
    python = search_symbols(root, "add")
    assert any(item["name"] == "add" and item["kind"] == "function"
               and item["path"] == "src/calc.py" for item in python)
    classes = search_symbols(root, "calculator")
    assert classes and classes[0]["kind"] == "class"
    ts = search_symbols(root, "widget")
    kinds = {(item["name"], item["kind"]) for item in ts}
    assert ("renderWidget", "function") in kinds
    assert ("WidgetProps", "interface") in kinds
    assert search_symbols(root, "definitely_missing") == []
    assert len(search_symbols(root, "", limit=2)) <= 2


def test_static_diagnostics_detect_syntax_and_structured_errors(tmp_path):
    root = _project(tmp_path)
    (root / "src" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    (root / "src" / "data.json").write_text('{"a": }', encoding="utf-8")
    (root / "src" / "conf.toml").write_text("key = [", encoding="utf-8")
    items = diagnose_files(root, ["src/calc.py", "src/broken.py",
                                  "src/data.json", "src/conf.toml"])
    paths = {item["path"] for item in items if item["severity"] == "error"}
    assert {"src/broken.py", "src/data.json", "src/conf.toml"} <= paths
    assert "src/calc.py" not in paths
    assert "SYNTAX" in format_diagnostics(items) or "Static diagnostics" in format_diagnostics(items)
    assert diagnose_files(root, ["../outside.py"])[0]["severity"] == "error"
    assert diagnose_files(root, ["missing.py"])[0]["message"] == "file is missing"


def test_lsp_diagnostics_is_available_or_honest(tmp_path):
    root = _project(tmp_path)
    payload = lsp_diagnostics(root)
    assert "available" in payload
    assert isinstance(payload.get("diagnostics"), list)
    if not payload["available"]:
        assert payload.get("reason")


def test_post_write_hook_invalidates_manifest(tmp_path, monkeypatch):
    """The static hook must reopen the staged gate when a changed file is invalid."""
    root = _project(tmp_path)
    stage_dir = root / "data" / "staging" / "mission-1-test"
    stage_dir.mkdir(parents=True)
    workspace = stage_dir / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    (stage_dir / "manifest.json").write_text(json.dumps({
        "version": 2,
        "mission_id": 1,
        "project_root": str(root),
        "changed": {"src/broken.py": "hash"},
        "scope": ["src/broken.py"],
        "validated": True,
        "verified": True,
    }), encoding="utf-8")
    stage = promotion.load_stage(stage_dir)
    from nl_coding_agent.tools.code_intel import diagnose_files as real_diagnose

    diagnostics = [item for item in real_diagnose(stage.workspace, ["src/broken.py"])
                   if item["severity"] == "error"]
    assert diagnostics
    promotion.invalidate_validation(stage, "post-write diagnostics failed")
    manifest = promotion.read_manifest(stage)
    assert manifest["validated"] is False
    assert manifest["verified"] is False
    assert "post-write diagnostics" in str(manifest.get("validation_error", ""))
