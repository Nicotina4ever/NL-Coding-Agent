"""Structured delegation uses real staging/verifier/promotion, scripted inference."""
import json
import threading
from pathlib import Path

import pytest

from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
from nl_coding_agent.cli import main
from nl_coding_agent.core import permissions, resource_gate
from nl_coding_agent.core.resource_gate import ResourceDecision
from nl_coding_agent.core.supervisor import Supervisor, SupervisorConfig
from nl_coding_agent.persistence import supervisor_store
from nl_coding_agent.persistence.missions import create_mission, get_mission
from nl_coding_agent.projects.registry import open_project


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src/__init__.py").write_text("")
    (root / "src/calc.py").write_text("def add(a,b): return a+b\n")
    (root / "tests").mkdir()
    (root / "tests/test_calc.py").write_text(
        "from src.calc import add\ndef test_add(): assert add(1,2)==3\n")
    monkeypatch.setattr(resource_gate, "decide", lambda *a, **k: ResourceDecision("run", "Test probe"))
    return open_project(root)


def test_json_cli_returns_evidence_from_real_verification(project, monkeypatch, capsys):
    seen = []
    def model(self, role, model_name, prompt, **kwargs):
        print("Verbose model output")
        seen.append(model_name)
        if role == "Implementation Developer":
            return "```write:src/calc.py\ndef add(a,b): return a+b\ndef subtract(a,b): return a-b\n```"
        return "APPROVE\n"
    monkeypatch.setattr(MultiAgentOrchestrator, "_call_model", model)
    code = main(["mission", "--json", "--project", project["root"],
                 "--goal", "Add subtract to src/calc.py", "--dev-model", "ollama/chosen-dev",
                 "--reviewer-model", "ollama/chosen-review", "--debug-model", "ollama/chosen-debug"])
    summary = json.loads(capsys.readouterr().out)
    assert code == 0 and summary["status"] == "completed", summary
    assert summary["promotion_status"] == "promoted"
    assert summary["changed_paths"] == ["src/calc.py"]
    assert summary["verification"] == {"runs": 2, "passed": 2}
    assert summary["models"] == {"developer": "ollama/chosen-dev", "reviewer": "ollama/chosen-review",
                                  "debug": "ollama/chosen-debug"}
    assert seen == ["ollama/chosen-dev", "ollama/chosen-review"]
    evidence = json.loads(Path(summary["artifacts"]["evidence"]).read_text(encoding="utf-8"))
    assert "def subtract" in evidence["result"]["mission_diff"]
    assert len(evidence["verification_runs"]) == 2
    assert "Verbose model output" in Path(summary["artifacts"]["log"]).read_text()
    assert supervisor_store.get_machine_lease(resource_gate.INFERENCE_RESOURCE) is None


def test_json_cli_permission_failure_is_nonzero_and_parseable(project, capsys):
    permissions.set_access_mode("read-only")
    code = main(["mission", "--json", "--project", project["root"], "--goal", "Update src/calc.py"])
    summary = json.loads(capsys.readouterr().out)
    assert code != 0 and summary["status"] == "blocked"
    assert "WRITE" in summary["error"]
    assert summary["verification"]["runs"] == 0


def test_json_cli_wrong_project_resume_preserves_mission(project, tmp_path, capsys):
    other = tmp_path / "other"; other.mkdir()
    mission_id = create_mission(project["id"], "Calculation", "Update src/calc.py")
    before = get_mission(mission_id)
    code = main(["mission", "--json", "--project", str(other), "--resume", str(mission_id)])
    summary = json.loads(capsys.readouterr().out)
    assert code != 0 and "requested project" in summary["error"]
    assert get_mission(mission_id) == before


def test_standalone_execution_renews_machine_slot_repeatedly(project, monkeypatch):
    config = SupervisorConfig(heartbeat_interval_s=0.2, lease_ttl_s=2)
    supervisor = Supervisor(project["root"], project_id=project["id"], config=config)
    mission_id = create_mission(project["id"], "Calculation", "Update src/calc.py")
    renewed = threading.Event()
    actual_renew = supervisor_store.renew_machine_lease
    versions = []
    def renew(*args, **kwargs):
        assert actual_renew(*args, **kwargs)
        versions.append(kwargs["version"])
        if len(versions) >= 2:
            renewed.set()
        return True
    monkeypatch.setattr(supervisor_store, "renew_machine_lease", renew)
    def invoke(*args):
        assert renewed.wait(4), "Standalone execution did not maintain inference ownership"
        return {"status": "blocked", "mission_id": mission_id}
    monkeypatch.setattr(supervisor, "_invoke_mission", invoke)
    supervisor.execute_mission(mission_id)
    assert versions[1] > versions[0]
    assert supervisor._heartbeat_thread is None
    assert supervisor_store.get_machine_lease(resource_gate.INFERENCE_RESOURCE) is None
