"""Foundation tests — Gate A validation."""
from __future__ import annotations

import sys
import sqlite3
import subprocess
import tempfile
from pathlib import Path
import pytest

# Ensure the workspace root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestCrewAIImports:
    def test_crewai_imports(self):
        from crewai import Agent, Crew, Task, LLM
        assert Agent is not None
        assert Crew is not None
        assert Task is not None
        assert LLM is not None

    def test_crewai_flow_import(self):
        from crewai.flow.flow import Flow
        assert Flow is not None


class TestDatabaseFoundation:
    def test_init_db_creates_tables(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_file = Path(f.name)
        conn = None
        try:
            from nl_coding_agent.persistence.database import init_db
            conn = init_db(db_file)
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            expected = ["projects", "project_facts", "model_inventory",
                        "missions", "tasks", "task_attempts", "app_settings", "events"]
            for t in expected:
                assert t in tables, f"Table {t} missing from DB"
        finally:
            if conn:
                conn.close()
            db_file.unlink(missing_ok=True)

    def test_log_event(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_file = Path(f.name)
        conn = None
        try:
            from nl_coding_agent.persistence.database import init_db, log_event
            conn = init_db(db_file)
            log_event(conn, "test message", source="test", level="info")
            row = conn.execute("SELECT * FROM events").fetchone()
            assert row is not None
            assert row["message"] == "test message"
        finally:
            if conn:
                conn.close()
            db_file.unlink(missing_ok=True)


class TestOllamaDetection:
    def test_ollama_check_does_not_raise(self):
        """Ollama may or may not be reachable — the call must not raise."""
        from nl_coding_agent.models.ollama_registry import check_ollama_reachable
        result = check_ollama_reachable()
        assert isinstance(result, bool)

    def test_list_models_returns_list(self):
        from nl_coding_agent.models.ollama_registry import list_models
        models = list_models()
        assert isinstance(models, list)
        # Each item should have a 'name' attribute
        for m in models:
            assert hasattr(m, "name")
            assert isinstance(m.name, str)


class TestProjectScanner:
    def test_scan_valid_directory(self):
        root = Path(__file__).resolve().parents[1]
        from nl_coding_agent.projects.scanner import scan_project
        facts = scan_project(root)
        assert "root" in facts
        assert "primary_language" in facts
        assert "file_count" in facts
        assert facts["file_count"] > 0

    def test_scan_rejects_nonexistent(self):
        from nl_coding_agent.projects.scanner import scan_project
        with pytest.raises(ValueError):
            scan_project(Path("/nonexistent/path/xyz123"))


class TestProjectRegistry:
    def test_open_project_round_trip(self, tmp_path):
        from nl_coding_agent.persistence.database import init_db
        from nl_coding_agent.projects import registry as reg

        # Patch database path for isolation
        import nl_coding_agent.persistence.database as dbmod
        orig = dbmod._DB_PATH
        test_db = tmp_path / "test.sqlite3"
        dbmod._DB_PATH = test_db

        try:
            # Create a simple test project directory
            project_dir = tmp_path / "myproject"
            project_dir.mkdir()
            (project_dir / "README.md").write_text("# Test")
            (project_dir / "main.py").write_text("print('hello')")

            project = reg.open_project(project_dir)
            assert project["name"] == "myproject"
            assert str(project_dir) in project["root"]

            recent = reg.list_recent()
            assert len(recent) >= 1
            assert any(p["name"] == "myproject" for p in recent)

            # Remove
            ok = reg.remove_project(project["id"])
            assert ok
            recent2 = reg.list_recent()
            assert not any(p["name"] == "myproject" for p in recent2)
        finally:
            dbmod._DB_PATH = orig
            # Reset singleton
            import nl_coding_agent.persistence.database as dbmod2
            dbmod2._DB_PATH = orig


class TestPySide6Available:
    def test_pyside6_importable(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        assert QApplication is not None

    def test_pyside6_svg(self):
        from PySide6.QtSvgWidgets import QSvgWidget
        assert QSvgWidget is not None
