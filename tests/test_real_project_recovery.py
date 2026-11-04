"""Regression shapes observed in NL_AudioLab mission #60, isolated from owner data."""
import asyncio
import base64
import json
from types import SimpleNamespace

import pytest

from nl_coding_agent.app.services import AppServices
from nl_coding_agent.app.mcp_engine import create_engine_server
from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator, _apply_text_actions
from nl_coding_agent.agents.crew_backend import FakeCrewRuntime
from nl_coding_agent.core import promotion
from nl_coding_agent.persistence import missions


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "Audio Project"
    (root / "scripts").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "scripts/app.py").write_text("def value():\n    return 0\n")
    (root / "tests/test_app.py").write_text("from scripts.app import value\ndef test_value():\n    assert value() == 1\n")
    services = AppServices()
    opened = services.open_project(root)
    yield services, opened, root
    services._db.close()


def test_root_context_is_not_a_file_scope_and_absolute_output_stays_in_stage(project):
    services, opened, root = project
    orch = MultiAgentOrchestrator(root, project_id=opened["id"], crew_runtime=FakeCrewRuntime({}))
    mid = missions.create_mission(opened["id"], "Fix", "Fix value in project " + str(root))
    tasks = orch._plan_tasks(mid, "Fix value in project `" + str(root) + "`")
    developer = next(item for item in tasks if item["agent_role"] == "developer")
    assert str(root) not in developer["write_paths"]
    stage = orch._ensure_stage(mid, developer, "Fix value")
    output = "```write:" + (root / "scripts/app.py").as_posix() + "\ndef value():\n    return 1\n```"
    actions = _apply_text_actions(stage.workspace, output, source_root=root, expected_paths=["scripts"])
    assert any("Wrote scripts/app.py" in item for item in actions)
    assert "return 1" in (stage.workspace / "scripts/app.py").read_text()
    assert "return 0" in (root / "scripts/app.py").read_text()
    escaped = output.replace((root / "scripts/app.py").as_posix(), (root.parent / "scripts/app.py").as_posix())
    assert "Skipped" in _apply_text_actions(stage.workspace, escaped, source_root=root, expected_paths=["scripts"])[0]


def test_catalog_survives_settings_refresh_and_uploaded_drop_uses_attachment_store(project, monkeypatch):
    services, opened, _ = project
    # engine_settings serializes a dataclass inventory, as in the real service.
    from nl_coding_agent.models.providers import ModelHubSnapshot
    monkeypatch.setattr(services, "discover_models", lambda **kwargs: ModelHubSnapshot(providers=[]))
    server = create_engine_server(services, opened)
    async def call(tool_name, **args):
        return await server._tool_manager.get_tool(tool_name).fn(**args)
    first = asyncio.run(call("engine_settings", include_models=True))
    again = asyncio.run(call("engine_settings", include_models=False))
    assert first["models"]["discovered"] == again["models"]["discovered"]
    attached = asyncio.run(call("attachment_ingest", name="AGENTS.md", file_base64=base64.b64encode(b"# Owner context\n").decode()))
    assert attached["ok"] and attached["attachments"][0]["name"] == "AGENTS.md"
    with pytest.raises(ValueError, match="base64"):
        asyncio.run(call("attachment_ingest", name="bad.md", file_base64="not base64!"))


def test_blocked_flow_resumes_same_mission_and_recovers_legacy_root_scope(project):
    from nl_coding_agent.core.supervisor import Supervisor, SupervisorConfig
    from nl_coding_agent.core.run_control import acknowledge_mission_resume
    services, opened, root = project
    goal = "Implement value() returning 1, preserve the tests. Project context: `" + root.as_posix() + "`"
    mid = missions.create_mission(opened["id"], "Mission 60 regression", goal)
    first_runtime = FakeCrewRuntime({"developer": ["I will implement it.", "I will implement it."]})
    config = SupervisorConfig(pipeline="flow", developer_model="ollama/fake", reviewer_model="ollama/fake", debug_model="ollama/fake")
    factory = lambda runtime: lambda root, **kwargs: MultiAgentOrchestrator(root, project_id=opened["id"], crew_runtime=runtime)
    first = Supervisor(root, project_id=opened["id"], config=config, orchestrator_factory=factory(first_runtime))
    initial_result = first._invoke_flow_mission(mid, None)
    assert initial_result["status"] == "blocked", initial_result
    before = missions.get_mission(mid)
    stage = promotion.load_stage(before["staging_dir"])
    manifest = promotion.read_manifest(stage)
    manifest["scope"] = [root.as_posix()]
    promotion._save_manifest(stage, manifest)
    with services._db:
        services._db.execute("UPDATE tasks SET write_paths=? WHERE mission_id=? AND agent_role='developer'", (json.dumps([root.as_posix()]), mid))
    acknowledge_mission_resume(mid, project_id=opened["id"])
    output = "```write:" + (root / "scripts/app.py").as_posix() + "\ndef value():\n    return 1\n```"
    runtime = FakeCrewRuntime({"developer": [output], "reviewer": ["APPROVE\nVerified change."]})
    resumed = Supervisor(root, project_id=opened["id"], config=config, orchestrator_factory=factory(runtime))
    result = resumed._invoke_flow_mission(mid, None)
    assert result["status"] == "completed", result
    assert missions.get_mission(mid)["flow_id"] == before["flow_id"]
    assert missions.get_mission(mid)["staging_dir"] == before["staging_dir"]
    assert missions.get_mission(mid)["promotion_status"] == "promoted"
    assert len([call for call in runtime.calls if call["role_id"] == "developer"]) == 1


def test_cloud_quota_switches_mission_agent_to_one_local_role_equivalent(project, monkeypatch):
    services, opened, root = project
    calls = []
    class Runtime:
        def run_agent(self, spec, prompt, **kwargs):
            calls.append(kwargs["model_name"])
            if kwargs["model_name"].endswith("cloud"):
                raise RuntimeError("429 monthly quota exhausted")
            return SimpleNamespace(text="local result", tool_invocations=())
    from nl_coding_agent.models import recovery
    monkeypatch.setattr(recovery, "local_equivalent", lambda *args: SimpleNamespace(provider_id="ollama", model_name="local-coder", selection={"role": "developer"}))
    orch = MultiAgentOrchestrator(root, project_id=opened["id"], crew_runtime=Runtime())
    from nl_coding_agent.agents.supervisor_executor import SupervisorMissionExecutor
    mid = missions.create_mission(opened["id"], "Cloud recovery", "Fix scripts/app.py")
    SupervisorMissionExecutor(orch, mid, "Fix scripts/app.py", developer_model="ollama/test-cloud").prepare()
    events = []
    capture = events.append
    services._bus.subscribe(capture)
    try:
        first = orch._call_model("developer", "ollama/test-cloud", "prompt", goal="goal", backstory="context", expected_output="code")
    finally:
        services._bus.unsubscribe(capture)
    assert any(event.source == "recovery" and event.payload["mission_id"] == mid for event in events)
    second = orch._call_model("developer", "ollama/test-cloud", "prompt", goal="goal", backstory="context", expected_output="code")
    assert first == second == "local result"
    assert calls == ["ollama/test-cloud", "ollama/local-coder", "ollama/local-coder"]
    assert orch._agent_metadata("ollama/test-cloud")["model"] == "ollama/local-coder"


def test_cloud_advisor_quota_preserves_isolation_when_falling_back_locally(project, monkeypatch):
    from nl_coding_agent.agents.subagents import SubagentRunner
    from nl_coding_agent.models import recovery
    services, opened, root = project
    calls = []
    class Runtime:
        def run_agent(self, spec, prompt, **kwargs):
            calls.append((spec.role_id, prompt, kwargs))
            if kwargs["model_name"] == "ollama/test-cloud":
                raise RuntimeError("429 quota exhausted")
            return SimpleNamespace(text="Local evidence", duration_s=1)
    monkeypatch.setattr(recovery, "local_equivalent", lambda *args: SimpleNamespace(provider_id="ollama", model_name="local-advisor"))
    result = SubagentRunner(root, opened["id"], Runtime()).run(name="Audio Advisor", objective="Inspect audio", model="ollama/test-cloud")
    assert result.model == "ollama/local-advisor"
    assert calls[0][0:2] == calls[1][0:2]
    assert calls[0][2]["tools"] is calls[1][2]["tools"]
    assert not {"write_file", "patch_file", "run_command"} & set(result.tools)


def test_explicit_resume_rechecks_failed_verification_with_a_fresh_repair_budget(project):
    from nl_coding_agent.core.supervisor import Supervisor, SupervisorConfig
    from nl_coding_agent.core.run_control import acknowledge_mission_resume
    services, opened, root = project
    goal = "Fix scripts/app.py value() to return 1 while preserving its definitions and all tests."
    mid = missions.create_mission(opened["id"], "Repair recovery", goal)
    wrong = "```write:scripts/app.py\ndef value():\n    return 0\n\ndef extra():\n    return 42\n```"
    correct = wrong.replace("return 0", "return 1")
    config = SupervisorConfig(pipeline="flow", developer_model="ollama/fake", reviewer_model="ollama/fake", debug_model="ollama/fake", max_attempts_per_requirement=1)
    def supervisor(runtime):
        return Supervisor(root, project_id=opened["id"], config=config,
            orchestrator_factory=lambda root, **kw: MultiAgentOrchestrator(root, project_id=opened["id"], crew_runtime=runtime))
    first = supervisor(FakeCrewRuntime({"developer": [wrong], "debugger": [wrong]}))
    initial_result = first._invoke_flow_mission(mid, None)
    assert initial_result["status"] == "blocked", initial_result
    acknowledge_mission_resume(mid, project_id=opened["id"])
    assert next(task for task in missions.get_tasks(mid) if task["agent_role"] == "tester")["status"] == "pending"
    runtime = FakeCrewRuntime({"debugger": [correct], "reviewer": ["APPROVE\nRechecked."]})
    result = supervisor(runtime)._invoke_flow_mission(mid, None)
    assert result["status"] == "completed", result
    assert len([item for item in runtime.calls if item["role_id"] == "debugger"]) == 1


def test_manual_specialists_allow_multiple_models_without_duplicate_execution_roles(project):
    services, opened, _ = project
    a = services.save_team_specialist(opened["id"], name="Advisor A", role_id="advisor", model="ollama/local", tools=[])
    b = services.save_team_specialist(opened["id"], name="Advisor Cloud", role_id="advisor", model="ollama/test-cloud", tools=[])
    first = services.save_team_specialist(opened["id"], name="Developer A", role_id="developer", model="ollama/local", tools=[])
    second = services.save_team_specialist(opened["id"], name="Developer B", role_id="developer", model="ollama/other", tools=[])
    active = [item for item in services.list_custom_agents() if item.get("team_active")]
    assert {item["id"] for item in active} == {a["id"], b["id"], second["id"]}
    assert first["id"] not in {item["id"] for item in active}


def test_automatic_team_is_project_specific_and_preserves_an_existing_team(project, monkeypatch):
    services, opened, root = project
    (root / "README.md").write_text("Audio restoration with MossFormer, waveform and PySide6 Qt6 workers.")
    from nl_coding_agent.models.providers import ModelHubSnapshot
    monkeypatch.setattr(services, "discover_models", lambda **kwargs: ModelHubSnapshot(providers=[]))
    monkeypatch.setattr(services, "get_model_config", lambda: {"roles": {"architect": {"model": "configured-architect"}}})
    routes = {"developer": "ollama/code", "reviewer": "ollama/review"}
    first = services.ensure_automatic_team(opened["id"], "Implement restoration", routes)
    assert {"architect", "developer", "debugger", "reviewer", "auditor"} <= {item["role_id"] for item in first}
    assert {"Audio / DSP Advisor", "Desktop / Qt Advisor"} <= {item["name"] for item in first}
    assert next(item for item in first if item["role_id"] == "architect")["model"] == "ollama/configured-architect"
    second = services.ensure_automatic_team(opened["id"], "Another task", {"developer": "ollama/different"})
    assert {item["id"] for item in first} == {item["id"] for item in second}


def test_invalid_developer_artifact_is_preserved_and_retry_starts_from_valid_candidate(project):
    services, opened, root = project
    goal = "Fix scripts/app.py value to return 1"
    mid = missions.create_mission(opened["id"], "Rejected candidate recovery", goal)
    orch = MultiAgentOrchestrator(root, project_id=opened["id"], crew_runtime=FakeCrewRuntime({
        "developer": ["```write:scripts/app.py\ndef value(:\n```"] * 2}))
    tasks = orch._plan_tasks(mid, goal)
    task = next(item for item in tasks if item["agent_role"] == "developer")
    stage = orch._ensure_stage(mid, task, goal)
    with pytest.raises(promotion.GateFailure, match="candidate rejected"):
        orch._run_developer_tasks(mid, tasks, goal, "ollama/fake", orch._snapshot(), stage)
    assert (stage.workspace / "scripts/app.py").read_text() == (root / "scripts/app.py").read_text()
    rejected = list((stage.stage_dir / "rejected-attempts").glob("*.json"))
    assert len(rejected) == 1 and "def value(:" in rejected[0].read_text()
    orch.crew_runtime = FakeCrewRuntime({"developer": ["```write:scripts/app.py\ndef value():\n    return 1\n```"]})
    orch._run_developer_tasks(mid, missions.get_tasks(mid), goal, "ollama/fake", orch._snapshot(), stage)
    assert "return 1" in (stage.workspace / "scripts/app.py").read_text()
    assert "return 0" in (root / "scripts/app.py").read_text()


def test_tool_loop_recovery_applies_a_plain_json_patch_once(project):
    services, opened, root = project
    class Runtime:
        calls = 0
        def run_agent(self, spec, prompt, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("not making progress: same arguments")
            return SimpleNamespace(text=json.dumps({"name": "patch_file", "arguments": {
                "path": "scripts/app.py", "target": "return 0", "replacement": "return 1"}}), tool_invocations=())
    runtime = Runtime()
    orch = MultiAgentOrchestrator(root, project_id=opened["id"], crew_runtime=runtime)
    goal = "Fix scripts/app.py value"
    mid = missions.create_mission(opened["id"], "Tool loop", goal)
    tasks = orch._plan_tasks(mid, goal)
    task = next(item for item in tasks if item["agent_role"] == "developer")
    stage = orch._ensure_stage(mid, task, goal)
    orch._run_developer_tasks(mid, tasks, goal, "ollama/fake", orch._snapshot(), stage)
    assert runtime.calls == 2
    assert "return 1" in (stage.workspace / "scripts/app.py").read_text()
    assert "return 0" in (root / "scripts/app.py").read_text()


def test_nested_project_git_evidence_excludes_sibling_changes(tmp_path):
    import subprocess
    from nl_coding_agent.tools.git_tools import get_git_diff, get_git_status
    parent = tmp_path / "parent"
    child = parent / "managed"
    child.mkdir(parents=True)
    outside = parent / "owner-private.txt"
    inside = child / "app.py"
    outside.write_text("outside before")
    inside.write_text("inside before")
    def git(*args):
        subprocess.run(["git", "-C", str(parent), *args], check=True, capture_output=True)
    git("init")
    git("add", ".")
    git("-c", "user.name=Acceptance", "-c", "user.email=acceptance@example.invalid", "commit", "-m", "baseline")
    outside.write_text("outside private after")
    inside.write_text("inside after")
    diff = get_git_diff(child)
    assert "inside after" in diff and "outside private after" not in diff
    assert "owner-private" not in get_git_status(child)


@pytest.mark.parametrize("failures,expected_status,expected_dispatches", [(1, "completed", 2), (10, "blocked", 3)])
def test_internal_failure_is_repaired_automatically_with_a_durable_limit(project, monkeypatch, failures, expected_status, expected_dispatches):
    services, opened, _ = project
    rt = services.session_runtime()
    rt.execution_allowed = True
    monkeypatch.setattr(rt, "start", lambda *args: None)
    sid = services.create_chat_session(opened["id"], "Recovery")["id"]
    rid = rt.submit(opened["id"], sid, "auto-repair", "Fix internal failure", allow_coding=True, mission_options={})["run_id"]
    calls = []
    def dispatch(mid, *args, **kwargs):
        calls.append(mid)
        status = "blocked" if len(calls) <= failures else "completed"
        missions.update_mission_status(mid, status)
        kwargs["on_done"]({"status": status, "code": "flow-blocked" if status == "blocked" else None})
    monkeypatch.setattr(services, "run_mission", dispatch)
    try:
        rt._execute(rid)
        assert rt.run(rid)["status"] == expected_status
        assert len(calls) == expected_dispatches and len(set(calls)) == 1
        assert rt.run(rid)["state"]["recovery_attempts"] == expected_dispatches - 1
        assert len([item for item in rt.snapshot(opened["id"], sid)["messages"] if item["role"] == "assistant"]) == 1
    finally:
        rt.close()


def test_automatic_repair_does_not_override_stop_or_uncertain_promotion(project, monkeypatch, tmp_path):
    services, opened, _ = project
    rt = services.session_runtime()
    rt.execution_allowed = True
    monkeypatch.setattr(rt, "start", lambda *args: None)
    sid = services.create_chat_session(opened["id"], "Stopped")["id"]
    rid = rt.submit(opened["id"], sid, "guarded", "Fix module", allow_coding=True, mission_options={})["run_id"]
    mission = missions.get_mission(rt.run(rid)["mission_id"])
    stage = tmp_path / "uncertain"
    stage.mkdir()
    (stage / promotion.PROMOTION_JOURNAL).write_text("{}")
    assert not rt._recover_internal_failure(rid, {**mission, "staging_dir": str(stage)}, {"code": "executor_exception"})
    from nl_coding_agent.persistence import database
    database.set_setting("mission.stop." + str(mission["id"]), "CLI stop")
    assert not rt.run(rid)["stop_requested"]
    assert not rt._recover_internal_failure(rid, mission, {"code": "flow-blocked"})
    assert database.get_setting("mission.stop." + str(mission["id"])) == "CLI stop"
    database.set_setting("mission.stop." + str(mission["id"]), "")
    rt.control(opened["id"], sid, "stop", run_id=rid, allow_execution=True)
    assert not rt._recover_internal_failure(rid, mission, {"code": "flow-blocked"})
    rt.close()


def test_scheduler_recovery_callback_can_requeue_the_same_mission_id():
    import threading
    from nl_coding_agent.resources.scheduler import SequentialScheduler
    scheduler = SequentialScheduler()
    done = threading.Event()
    calls = []
    def finished(result):
        calls.append(result)
        if len(calls) == 1:
            scheduler.submit("same", lambda: "recovered", on_done=finished)
        else:
            done.set()
    try:
        scheduler.submit("same", lambda: "failed", on_done=finished)
        assert done.wait(5)
        assert calls == ["failed", "recovered"]
    finally:
        scheduler.shutdown()
