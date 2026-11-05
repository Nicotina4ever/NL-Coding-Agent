"""Goal continuation through the existing queue and real staged verifier.

Only inference is scripted here. Candidate/oracle subprocesses and promotion are real;
this file does not claim real-model acceptance.
"""
import json
from pathlib import Path

import pytest

from nl_coding_agent.core.goals import GoalService
from nl_coding_agent.core.supervisor import Supervisor, SupervisorConfig
from nl_coding_agent.core.resource_gate import ResourceDecision
from nl_coding_agent.persistence import supervisor_store as store, goal_store
from nl_coding_agent.persistence.missions import get_mission, get_verification_runs
from nl_coding_agent.projects.registry import open_project
from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "state"))
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src/__init__.py").write_text("")
    (root / "src/calc.py").write_text("def add(a,b): return a+b\n")
    (root / "tests").mkdir()
    (root / "tests/test_calc.py").write_text(
        "from src.calc import add\ndef test_add(): assert add(1,2)==3\n")
    project = open_project(root)
    return root, project["id"], GoalService()


def plan_goal(service, project_id, *, priority="P1", count=2, approve=True):
    goal = service.create_goal("Extend calculation safely", project_id=project_id,
                               acceptance_criteria=["Baseline arithmetic remains green"], priority=priority)
    service.replan_goal(goal["id"], [
        {"key": str(i), "title": "Step " + str(i),
         "mission_intent": "Add function step" + str(i) + " to src/calc.py",
         "acceptance_criteria": ["Baseline arithmetic remains green"],
         "validation_strategy": "Run candidate and baseline oracle tests",
         "dependencies": [str(i-1)] if i else []}
        for i in range(count)], "Implementation plan")
    service.activate_goal(goal["id"])
    if approve:
        service.approve_plan(goal["id"], rationale="Reviewed executable milestones")
    return service.get_goal(goal["id"])


def supervisor(env, factory=None, control=None, **overrides):
    root, project_id, _ = env
    config = SupervisorConfig(mode="automatic", work_source="goals",
                              backoff_schedule_s=(0,), **overrides)
    return Supervisor(root, project_id=project_id, config=config,
                      orchestrator_factory=factory, control=control,
                      resource_decider=lambda *a, **kw: ResourceDecision("run", "Test resource probe"))


def scripted_factory(calls, hook=None):
    def factory(root):
        orch = MultiAgentOrchestrator(root)
        def call(role, model, prompt, **kwargs):
            calls.append(role)
            if role == "Implementation Developer":
                if hook: hook()
                # Cumulative edits survive the next mission baseline.
                # Use call count to produce a different, relevant change for each mission.
                number = calls.count("Implementation Developer")
                code = "def add(a,b): return a+b\n" + "".join(
                    f"def step{i}(): return {i}\n" for i in range(number))
                return "```write:src/calc.py\n" + code + "```"
            return "APPROVE\nCandidate has independent candidate/oracle evidence."
        orch._call_model = call
        return orch
    return factory


def test_two_dependent_missions_run_and_restart_reuses_progress(env):
    root, project_id, service = env
    goal = plan_goal(service, project_id)
    calls = []
    first = supervisor(env, scripted_factory(calls)).run(max_missions=1)
    assert first["completed"] == 1, first
    milestones = service.list_milestones(goal["id"])
    assert [m["status"] for m in milestones] == ["completed", "pending"]
    assert service.get_goal(goal["id"])["status"] == "active"
    links = service.list_goal_links(goal["id"])
    assert len(links) == 1
    assert get_mission(links[0]["mission_id"])["promotion_status"] == "promoted"
    assert len(get_verification_runs(links[0]["mission_id"])) == 2
    second = supervisor(env, scripted_factory(calls)).run(max_missions=1)
    assert second["completed"] == 1, second
    assert all(m["status"] == "completed" for m in service.list_milestones(goal["id"]))
    assert len(service.list_goal_links(goal["id"])) == 2
    third = supervisor(env, scripted_factory(calls)).run(max_missions=1)
    assert third["status"] == "idle", third
    assert calls.count("Implementation Developer") == 2


def test_unapproved_paused_mutated_and_other_project_never_execute(env):
    _, pid, service = env
    goal = plan_goal(service, pid, approve=False)
    assert service.select_execution(pid)["selected"] is None
    service.approve_plan(goal["id"], rationale="reviewed")
    assert service.select_execution(pid + 1)["selected"] is None
    assert service.select_execution(pid)["selected"]
    service.pause_goal(goal["id"])
    assert supervisor(env).enqueue_next() is None
    service.resume_goal(goal["id"])
    milestone = service.list_milestones(goal["id"])[0]
    service.update_milestone(milestone["id"], mission_intent="Changed without approval")
    decision = service.select_execution(pid)
    assert decision["selected"] is None
    assert "changed after plan approval" in decision["deferred"][0]["reason"]


def test_priority_and_idempotent_queue_selection(env):
    _, pid, service = env
    low = plan_goal(service, pid, priority="P2", count=1)
    high = plan_goal(service, pid, priority="P0", count=1)
    sup = supervisor(env)
    one = sup._next_queue_item()
    two = supervisor(env)._next_queue_item()
    assert one["id"] == two["id"]
    assert one["payload"]["goal_id"] == high["id"]
    assert len(store.list_queue(pid)) == 1


def test_false_completed_claim_cannot_advance_milestone(env):
    _, pid, service = env
    goal = plan_goal(service, pid, count=1)
    class FalseCompletion:
        def run_mission(self, **kw): return {"status": "completed", "mission_id": kw["mission_id"]}
    result = supervisor(env, lambda root: FalseCompletion()).run(max_missions=1)
    assert result["status"] == "blocked", result
    assert result["completed"] == 0
    assert service.list_milestones(goal["id"])[0]["status"] == "pending"
    assert store.list_queue(pid)[0]["state"] == "BLOCKED"


def test_pause_at_stage_boundary_prevents_live_write(env):
    root, pid, service = env
    goal = plan_goal(service, pid, count=1)
    before = (root / "src/calc.py").read_text()
    calls = []
    result = supervisor(env, scripted_factory(calls, lambda: service.pause_goal(goal["id"]))).run()
    assert result["status"] == "stopped", result
    assert calls == ["Implementation Developer"]
    assert (root / "src/calc.py").read_text() == before
    assert store.list_queue(pid)[0]["state"] == "INTERRUPTED"


def test_manually_checked_dependency_does_not_authorize_execution(env):
    _, pid, service = env
    goal = plan_goal(service, pid)
    first, second = service.list_milestones(goal["id"])
    service.update_milestone(first["id"], status="completed")
    decision = service.select_execution(pid)
    assert decision["selected"] is None
    assert "lacks independent execution evidence" in decision["deferred"][0]["reason"]


def test_external_run_control_keeps_goal_checkpoint_policy(env):
    from nl_coding_agent.core.run_control import RunControl
    root, pid, service = env
    goal = plan_goal(service, pid, count=1)
    calls, checkpoints = [], []
    control = RunControl(on_checkpoint=checkpoints.append)
    result = supervisor(env, scripted_factory(calls, lambda: service.pause_goal(goal["id"])),
                        control=control).run()
    assert result["status"] == "stopped", result
    assert "after-developer" in checkpoints
    assert calls == ["Implementation Developer"]
    assert (root / "src/calc.py").read_text() == "def add(a,b): return a+b\n"


def test_resume_command_retains_goal_source(env):
    assert "--work-source goals" in supervisor(env)._resume_command()


def test_crash_after_binding_recovers_same_mission_and_claim(env):
    _, pid, service = env
    goal = plan_goal(service, pid, count=1)
    sup = supervisor(env)
    item = sup._next_queue_item()
    store.claim_queue_item(item["id"], claim_token="crashed", owner_id="previous-owner")
    mid = store.bind_goal_mission(item["id"], project_id=pid,
                                 claim_token="crashed", supervisor_run_id=None)
    store.update_queue_item(item["id"], claim_token="crashed", state="RUNNING")
    calls = []
    result = supervisor(env, scripted_factory(calls)).run()
    assert result["completed"] == 1, result
    assert len(service.list_goal_links(goal["id"])) == 1
    assert store.get_queue_item(item["id"])["mission_id"] == mid
    assert service.list_milestones(goal["id"])[0]["status"] == "completed"


def test_historical_verified_queue_does_not_break_replan_recovery(env):
    _, pid, service = env
    goal = plan_goal(service, pid, count=1)
    assert supervisor(env, scripted_factory([])).run()["completed"] == 1
    service.replan_goal(goal["id"], [{"key": "new", "title": "Replacement milestone",
                                   "mission_intent": "Update src/calc.py"}], "Scope changed")
    result = supervisor(env).run()
    assert result["status"] == "idle", result
    assert service.list_milestones(goal["id"])[0]["status"] == "pending"


def test_pause_during_review_is_checked_before_promotion(env):
    root, pid, service = env
    goal = plan_goal(service, pid, count=1)
    calls = []
    base_factory = scripted_factory(calls)
    def factory(root):
        orch = base_factory(root)
        original = orch._call_model
        def call(role, *args, **kwargs):
            output = original(role, *args, **kwargs)
            if role == "Code Reviewer & Quality Gatekeeper":
                service.pause_goal(goal["id"])
            return output
        orch._call_model = call
        return orch
    result = supervisor(env, factory).run()
    assert result["status"] == "stopped", result
    assert calls[-1] == "Code Reviewer & Quality Gatekeeper"
    assert (root / "src/calc.py").read_text() == "def add(a,b): return a+b\n"


def test_plan_approval_does_not_replace_project_permissions(env):
    from nl_coding_agent.core import permissions
    _, pid, service = env
    plan_goal(service, pid, count=1)
    permissions.set_access_mode("read-only")
    result = supervisor(env).run()
    assert result["status"] == "blocked", result
    assert store.list_queue(pid) == []


def test_goal_source_cli_and_background_facade_forwarding(env, monkeypatch, capsys):
    from nl_coding_agent import cli
    from nl_coding_agent.core import supervisor as module
    from nl_coding_agent.app.supervisor_service import SupervisorService
    seen = []
    def runner(*a, **kw):
        seen.append(kw)
        return {"status": "idle", "missions": [], "resume_command": ""}
    monkeypatch.setattr(module, "run_supervisor", runner)
    code = cli.main(["supervisor", "run", "--project", str(env[0]),
                     "--work-source", "goals", "--json"])
    assert code == 0
    assert seen[-1]["work_source"] == "goals"
    background = SupervisorService(env[0], env[1], supervisor_runner=runner)
    assert background.start(work_source="goals")["ok"]
    assert background.wait(5)["status"] == "idle"
    assert seen[-1]["work_source"] == "goals"


def test_status_after_restart_keeps_goal_resume_source(env):
    _, pid, service = env
    plan_goal(service, pid, count=1)
    assert supervisor(env, scripted_factory([])).run()["completed"] == 1
    # A new status reader starts with default backlog config, as the GUI does.
    reader = Supervisor(env[0], project_id=pid)
    status = reader.status()
    assert status["work_source"] == "goals"
    assert "--work-source goals" in status["resume_command"]


def test_detached_cli_preserves_source_pipeline_and_assisted_consent(env, monkeypatch, capsys):
    from nl_coding_agent import cli
    command = []
    monkeypatch.setattr(cli, "_launch_detached", lambda args, log: command.extend(args) or 123)
    assert cli.main(["supervisor", "start", "--project", str(env[0]),
                     "--work-source", "goals", "--pipeline", "flow",
                     "--mode", "assisted", "--confirm-assisted", "--json"]) == 0
    assert command[command.index("--work-source") + 1] == "goals"
    assert command[command.index("--pipeline") + 1] == "flow"
    assert "--confirm-assisted" in command
