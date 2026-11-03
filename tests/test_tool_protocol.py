"""Validated tool protocol, invocation ledger and patch parser regression tests."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from nl_coding_agent.agents.crew_backend import _invocations_from_output
from nl_coding_agent.agents.orchestrator import _apply_text_actions
from nl_coding_agent.core import tool_invocations
from nl_coding_agent.tools.filesystem import scoped_patch_file


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    from nl_coding_agent.persistence import database
    database.init_db().close()
    return tmp_path / "data"


def test_malformed_python_patch_call_is_applied_without_execution(tmp_path, isolated_db):
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("A = 1\nB = 2\n", encoding="utf-8")
    diff = (
        "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n"
        " A = 1\n-B = 2\n+B = 3\n"
    )
    text = "```python\npatch_file('a.py', '''" + diff + "''')\nprint('x')\n```"
    actions = _apply_text_actions(root, text)
    assert any("a.py" in item for item in actions)
    assert (root / "a.py").read_text(encoding="utf-8") == "A = 1\nB = 3\n"


def test_python_keyword_and_three_positional_patch_calls(tmp_path, isolated_db):
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("A = 1\nB = 2\n", encoding="utf-8")
    keyword_text = (
        "```python\npatch_file(path='a.py', target='B = 2', replacement='B = 3')\n```"
    )
    assert any("a.py" in item for item in _apply_text_actions(root, keyword_text))
    assert (root / "a.py").read_text(encoding="utf-8") == "A = 1\nB = 3\n"
    positional_text = (
        "```python\npatch_file('a.py', 'A = 1', 'A = 4')\n```"
    )
    assert any("a.py" in item for item in _apply_text_actions(root, positional_text))
    assert (root / "a.py").read_text(encoding="utf-8") == "A = 4\nB = 3\n"


def test_fenced_json_line_patch_calls_are_applied(tmp_path, isolated_db):
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("A = 1\nB = 2\n", encoding="utf-8")
    text = (
        "```python\n"
        '{"name": "patch_file", "arguments": {"path": "a.py", '
        '"target": "B = 2", "replacement": "B = 5"}}\n'
        "```"
    )
    actions = _apply_text_actions(root, text)
    assert any("Patched a.py" in item for item in actions)
    assert (root / "a.py").read_text(encoding="utf-8") == "A = 1\nB = 5\n"


def test_empty_patch_target_is_rejected(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("A = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty patch target"):
        scoped_patch_file(root, "a.py", "", "X")


def test_invocation_ledger_distinguishes_available_from_invoked(tmp_path, isolated_db):
    tool_invocations.record_invocation(
        "read_file", arguments={"path": "a.py"}, result="ok",
        project_id=None, mission_id=None, session_id="s1", role="chat",
    )
    rows = tool_invocations.list_invocations(session_id="s1")
    assert rows[0]["tool_name"] == "read_file"
    assert rows[0]["source"] == "native"
    assert rows[0]["arguments_json"] == {"path": "a.py"}


def test_crew_output_extracts_real_calls_and_error_results():
    output = SimpleNamespace(tasks_output=[SimpleNamespace(messages=[
        SimpleNamespace(role="assistant", tool_calls=[{
            "id": "c1", "function": {"name": "patch_file",
                                     "arguments": json.dumps({"path": "a.py"})},
        }]),
        SimpleNamespace(role="tool", tool_call_id="c1", name="patch_file",
                        content="Error patching file 'a.py': target not found"),
    ])])
    invocations = _invocations_from_output(output)
    assert len(invocations) == 1
    assert invocations[0]["tool_name"] == "patch_file"
    assert invocations[0]["status"] == "completed"
    assert invocations[0]["arguments"] == {"path": "a.py"}
    assert "target not found" in invocations[0]["result"]

def test_comment_labelled_complete_files_are_applied(tmp_path, isolated_db):
    root = tmp_path / "project"
    root.mkdir()
    (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (root / "test_calc.py").write_text("from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8")
    text = (
        "```python\n# calc.py\n"
        "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n"
        "```\n"
        "```python\n# test_calc.py\n"
        "from calc import add, subtract\n\ndef test_add():\n    assert add(2, 3) == 5\n\n"
        "def test_subtract():\n    assert subtract(5, 3) == 2\n"
        "```"
    )
    actions = _apply_text_actions(root, text, expected_paths=["calc.py", "test_calc.py"])
    assert any("calc.py" in item for item in actions)
    assert "def subtract" in (root / "calc.py").read_text(encoding="utf-8")
    assert "test_subtract" in (root / "test_calc.py").read_text(encoding="utf-8")
