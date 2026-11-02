"""P3 skills: discovery, progressive catalog, on-demand load, tool exposure."""
from __future__ import annotations

import json

import pytest

from nl_coding_agent.app.services import AppServices
from nl_coding_agent.context.engine import ContextEngine
from nl_coding_agent.skills import SkillCatalog, discover_skills
from nl_coding_agent.tools.crew_tools import get_project_tools


def _write_skill(root, name: str, description: str, body: str):
    directory = root / ".agents" / "skills" / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: " + name + "\ndescription: " + description + "\n"
        "when_to_use: when " + description.lower() + "\n---\n\n" + body,
        encoding="utf-8",
    )


@pytest.fixture
def skill_project(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    _write_skill(root, "verify-tests", "Always run pytest before claiming success",
                 "1. Run the project test command.\n2. Paste the real output.\n"
                 "3. Never claim a pass without output.")
    _write_skill(root, "api-conventions", "Project HTTP API conventions",
                 "Use typed request models and return explicit error codes.")
    (root / ".nlcode" / "skills").mkdir(parents=True)
    (root / ".nlcode" / "skills" / "release.json").write_text(json.dumps({
        "name": "release-checklist",
        "description": "Release steps",
        "instructions": "Build, run smoke tests, record checksums.",
    }), encoding="utf-8")
    services = AppServices()
    opened = services.open_project(root)
    yield services, opened, root
    services._db.close()


def test_skills_are_discovered_with_metadata(skill_project):
    _services, _opened, root = skill_project
    names = {item.name for item in discover_skills(root)}
    assert {"verify-tests", "api-conventions", "release-checklist"} <= names
    catalog = SkillCatalog(root)
    text = catalog.catalog_text()
    assert "verify-tests" in text and "Always run pytest" in text
    assert "1. Run the project test command" not in text  # progressive: body not loaded yet
    loaded = catalog.load_text("verify-tests")
    assert "1. Run the project test command" in loaded
    assert "guidance, not authorization" in loaded.lower()
    assert "Unknown skill" in catalog.load_text("missing-skill")


def test_skill_tools_are_read_only_and_available(skill_project):
    _services, _opened, root = skill_project
    read_only = {tool.name for tool in get_project_tools(root, read_only=True)}
    assert {"list_skills", "load_skill"} <= read_only
    tools = {tool.name: tool for tool in get_project_tools(root)}
    assert "load_skill" in tools
    # Tool objects are CrewAI tools; invoking the wrapped function is not required here,
    # the handler contract is covered by the chat/mission tests.


def test_mission_context_pack_includes_the_skill_catalog(skill_project):
    _services, opened, root = skill_project
    engine = ContextEngine(opened["id"], root)
    pack = engine.build_mission_pack("Fix add in src/calc.py", budget_chars=8_000)
    assert pack.skills_catalog
    assert "verify-tests" in pack.skills_catalog
    developer = pack.for_role("developer")
    reviewer = pack.for_role("reviewer")
    assert "verify-tests" in developer and "verify-tests" in reviewer
    assert pack.to_dict()["skills_catalog"] is True
