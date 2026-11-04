"""Durable acceptance, session isolation, dispatcher and recovery boundaries."""
import json
import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from nl_coding_agent.app.services import AppServices
from nl_coding_agent.app.session_runtime import RuntimeTurn
from nl_coding_agent.persistence import database


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "project"
    root.mkdir()
    (root / "calc.py").write_text("value = 7\n")
    services = AppServices()
    project = services.open_project(root)
    session = services.create_chat_session(project["id"], "First")
    runtime = services.session_runtime()
    runtime.execution_allowed = True
    yield runtime, services, project["id"], session["id"]
    runtime.close()
    for thread in runtime._threads.values():
        thread.join(5)
    services._db.close()


def wait_status(runtime, rid, wanted="completed"):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        run = runtime.run(rid)
        if run["status"] == wanted:
            return run
        time.sleep(.03)
    pytest.fail(f"Expected {wanted}, got {runtime.run(rid)}")


def test_concurrent_duplicate_acceptance_has_one_message_and_one_turn(runtime, monkeypatch):
    rt, services, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *args: None)
    with ThreadPoolExecutor(8) as pool:
        accepted = list(pool.map(lambda _: rt.submit(pid, sid, "same-request", "hello"), range(12)))
    assert len({item["run_id"] for item in accepted}) == 1
    assert len(services.list_chat_messages(project_id=pid, session_id=sid)) == 1
    with pytest.raises(ValueError, match="different content"):
        rt.submit(pid, sid, "same-request", "different")


def test_explicit_mcp_mission_is_idempotent_and_finishes_in_its_session_without_ui(runtime, monkeypatch):
    from nl_coding_agent.app.mcp_engine import create_engine_server
    from nl_coding_agent.persistence.missions import get_mission, update_mission_status
    rt, services, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *args: None)
    server = create_engine_server(services, services.get_project(pid), allow_execution=True)
    async def invoke(name, **kwargs):
        return await server._tool_manager.get_tool(name).fn(**kwargs)
    args = dict(goal="Fix calc.py", developer_model="ollama/developer", reviewer_model="ollama/reviewer",
                approved=True, session_id=sid, request_id="explicit-mission")
    first = asyncio.run(invoke("start_mission", **args))
    duplicate = asyncio.run(invoke("start_mission", **args))
    assert first["mission_id"] == duplicate["mission_id"]
    rid, mid = first["session_run_id"], first["mission_id"]
    assert rt.mission_run(pid, mid)["id"] == rid
    calls = []
    def execute(mission_id, root, **options):
        calls.append(options)
        update_mission_status(mission_id, "completed")
        options["on_done"]({"status": "completed"})
    monkeypatch.setattr(services, "run_mission", execute)
    rt._execute(rid)
    assert rt.run(rid)["status"] == "completed"
    assert calls[0]["developer_model"] == "ollama/developer"
    assert calls[0]["reviewer_model"] == "ollama/reviewer"
    assert rt.snapshot(pid, sid)["messages"][-1]["mission_id"] == mid
    other = services.create_chat_session(pid, "Other")["id"]
    update_mission_status(mid, "interrupted")
    rt._status(rid, "interrupted", {"reply": "Retained"})
    resumed = asyncio.run(invoke("start_mission", **{**args, "goal": get_mission(mid)["goal"],
        "session_id": other, "request_id": "resume", "resume_mission_id": mid, "developer_model": "ollama/replacement"}))
    assert resumed["session_run_id"] == rid and resumed["session_id"] == sid
    assert rt.run(rid)["status"] == "queued"
    assert rt.run(rid)["payload"]["mission_options"]["developer_model"] == "ollama/replacement"
    stopped = asyncio.run(invoke("cancel_mission", mission_id=mid, approved=True))
    assert stopped["accepted"]
    with rt.db() as conn:
        assert conn.execute("SELECT 1 FROM session_pauses WHERE session_id=?", (sid,)).fetchone()
        assert conn.execute("SELECT count(*) FROM missions").fetchone()[0] == 1
    assert not rt.snapshot(pid, other)["messages"]


def test_stop_before_explicit_mission_dispatch_retains_a_resumable_mission(runtime, monkeypatch):
    from nl_coding_agent.persistence.missions import get_mission
    rt, _, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *args: None)
    rid = rt.submit(pid, sid, "queued-mission", "Fix calc.py", allow_coding=True,
                    mission_options={"developer_model": "ollama/local"})["run_id"]
    mid = rt.run(rid)["mission_id"]
    rt.control(pid, sid, "stop", run_id=rid, allow_execution=True)
    assert get_mission(mid)["status"] == "interrupted"
    rt.control(pid, sid, "resume", run_id=rid, allow_execution=True)
    assert rt.run(rid)["status"] == "queued"


def test_retry_point_and_models_commit_only_with_a_successful_resume(runtime, monkeypatch):
    rt, _, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *args: None)
    rid = rt.submit(pid, sid, "retry-mission", "Fix calc.py", allow_coding=True,
                    mission_options={"developer_model": "ollama/original"})["run_id"]
    mid = rt.run(rid)["mission_id"]
    with rt.db() as conn, conn:
        tid = conn.execute("INSERT INTO tasks(mission_id,title,status) VALUES(?,'Fix','completed')", (mid,)).lastrowid
    rt.control(pid, sid, "stop", run_id=rid, allow_execution=True)
    with pytest.raises(ValueError, match="No task"):
        rt.control(pid, sid, "resume", run_id=rid, allow_execution=True,
                   retry_from_task_id=tid + 1000, mission_options={"developer_model": "ollama/wrong"})
    assert rt.run(rid)["status"] == "cancelled"
    assert rt.run(rid)["payload"]["mission_options"]["developer_model"] == "ollama/original"
    rt.control(pid, sid, "resume", run_id=rid, allow_execution=True, retry_from_task_id=tid)
    with rt.db() as conn, conn:
        conn.execute("UPDATE tasks SET status='running' WHERE id=?", (tid,))
    with pytest.raises(ValueError, match="not resumable"):
        rt.control(pid, sid, "resume", run_id=rid, allow_execution=True, retry_from_task_id=tid)
    with rt.db() as conn:
        assert conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()[0] == "running"


def test_resume_waits_for_current_dispatch_instead_of_previous_terminal_mission(runtime, monkeypatch):
    from nl_coding_agent.persistence.missions import update_mission_status
    rt, services, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *args: None)
    rid = rt.submit(pid, sid, "resume-wait", "Fix calc.py", allow_coding=True, mission_options={})["run_id"]
    mid = rt.run(rid)["mission_id"]
    update_mission_status(mid, "interrupted")
    scheduled = threading.Event()
    callbacks = []
    def dispatch(*args, **options):
        callbacks.append(options["on_done"])
        scheduled.set()
    monkeypatch.setattr(services, "run_mission", dispatch)
    worker = threading.Thread(target=rt._execute, args=(rid,))
    worker.start()
    try:
        assert scheduled.wait(5)
        time.sleep(1)
        assert rt.run(rid)["status"] == "waiting_mission"
        update_mission_status(mid, "completed")
        callbacks[0]({"status": "completed"})
        worker.join(5)
        assert rt.run(rid)["status"] == "completed"
    finally:
        rt._closed.set()
        worker.join(5)


def test_turn_replies_to_selected_session_and_replays_events(runtime, monkeypatch):
    rt, services, pid, sid = runtime
    other = services.create_chat_session(pid, "Second")["id"]
    class Provider:
        provider_id = "test"
        def chat_turn_stream(self, model, messages, tools, **options):
            assert messages[-1]["content"] == "selected session"
            options["on_delta"]("Risposta ")
            options["on_delta"]("reale")
            return {"content": "Risposta reale"}
    monkeypatch.setattr(services, "_resolve_chat_provider", lambda *a, **kw: (Provider(), "test", "test", ""))
    rid = rt.submit(pid, sid, "request", "selected session")["run_id"]
    wait_status(rt, rid)
    assert not services.list_chat_messages(project_id=pid, session_id=other)
    messages = services.list_chat_messages(project_id=pid, session_id=sid)
    assert messages[-1]["content"] == "Risposta reale"
    batch = rt.events(pid, sid)
    assert any(e["type"] == "assistant.delta" for e in batch["events"])
    assert not rt.events(pid, sid, batch["cursor"])["events"]


def test_queue_survives_dispatch_failure_and_requires_explicit_resume(runtime, monkeypatch):
    rt, services, pid, sid = runtime
    monkeypatch.setattr(services, "chat_conversation", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline")))
    rid = rt.submit(pid, sid, "request", "hello")["run_id"]
    wait_status(rt, rid, "failed")
    assert rt.run(rid)["payload"]["text"] == "hello"
    assert rt.snapshot(pid, sid)["messages"][-1]["content"] == "offline"
    assert rt.run(rid)["status"] == "failed"
    monkeypatch.setattr(services, "chat_conversation", lambda *a, **kw: {"ok": True, "reply": "back"})
    rt.control(pid, sid, "resume", run_id=rid)
    wait_status(rt, rid)


def test_steering_order_and_consumption_are_session_scoped(runtime, monkeypatch):
    rt, services, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *args: None)
    rid = rt.submit(pid, sid, "request", "hello")["run_id"]
    with rt.db() as conn, conn:
        conn.execute("UPDATE session_runs SET status='running' WHERE id=?", (rid,))
    rt.control(pid, sid, "steer", run_id=rid, text="First constraint")
    rt.control(pid, sid, "steer", run_id=rid, text="Second constraint")
    rows = rt.take_steering(rid, "developer")
    assert [item["text"] for item in rows] == ["First constraint", "Second constraint"]
    assert not rt.take_steering(rid, "reviewer")
    other = services.create_chat_session(pid, "Other")["id"]
    with pytest.raises(ValueError, match="another session"):
        rt.control(pid, other, "stop", run_id=rid)


def test_crashed_effect_is_not_replayed(runtime, monkeypatch):
    rt, _, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *a: None)
    rid = rt.submit(pid, sid, "request", "hello")["run_id"]
    with rt.db() as conn, conn:
        conn.execute("UPDATE session_runs SET status='running',owner='dead',lease_until=0,state_json=? WHERE id=?",
                     (json.dumps({"in_flight": "write-uncertain"}), rid))
    assert rt._lease(pid)
    assert rt.run(rid)["status"] == "interrupted"
    with pytest.raises(ValueError, match="uncertain"):
        rt.control(pid, sid, "resume", run_id=rid)


def test_mission_creation_and_link_are_idempotent(runtime, monkeypatch):
    rt, _, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *a: None)
    rid = rt.submit(pid, sid, "request", "fix module", allow_coding=True)["run_id"]
    first = rt.prepare_mission(rid, "fix module")
    assert rt.prepare_mission(rid, "fix module") == first
    assert rt.run(rid)["mission_id"] == first


def test_legacy_import_is_suspended_idempotent_and_preserves_original(runtime, monkeypatch):
    rt, _, pid, _ = runtime
    path = database.data_root() / "chat" / f"queue-project-{pid}.json"
    path.parent.mkdir(exist_ok=True)
    original = '[{"text":"previous request"}]'
    path.write_text(original)
    rt.migrate_legacy(pid)
    rt.migrate_legacy(pid)
    with rt.db() as conn:
        rows = conn.execute("SELECT * FROM session_runs WHERE project_id=?", (pid,)).fetchall()
    assert len(rows) == 1 and rows[0]["status"] == "interrupted"
    assert path.read_text() == original


def test_stop_is_durable_and_queued_work_does_not_start(runtime, monkeypatch):
    rt, _, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *a: None)
    rid = rt.submit(pid, sid, "request", "hello")["run_id"]
    rt.control(pid, sid, "stop", run_id=rid)
    assert RuntimeTurn(rt, rid).cancelled()
    assert rt.run(rid)["status"] == "cancelled"
    with pytest.raises(ValueError, match="Conversation stopped"):
        rt.submit(pid, sid, "later", "do not silently enqueue")


def test_resume_prepared_mission_dispatches_once_and_ignores_old_outcome(runtime, monkeypatch):
    rt, services, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *a: None)
    rid = rt.submit(pid, sid, "request", "fix module", allow_coding=True)["run_id"]
    mid = rt.prepare_mission(rid, "fix module")
    rt.save_state(rid, {"dispatch_pending": [{"mission_id": mid}]})
    rt.emit(sid, rid, "mission.dispatch_result", {"status": "failed", "dispatch_generation": "old"})
    calls = []
    def dispatch(*args, **kwargs):
        calls.append(args[0])
        from nl_coding_agent.persistence.missions import update_mission_status
        update_mission_status(mid, "completed")
        with rt.db() as conn, conn:
            conn.execute("UPDATE missions SET changed_paths=? WHERE id=?", ('["src/calc.py"]', mid))
        kwargs["on_done"]({"status": "completed"})
    monkeypatch.setattr(services, "run_mission", dispatch)
    rt._execute(rid)
    assert calls == [mid]
    assert not rt.run(rid)["state"]["dispatch_pending"]
    assert rt.run(rid)["status"] == "completed"
    assert rt.run(rid)["result"]["changed_paths"] == ["src/calc.py"]
    assert "File modificati: src/calc.py" in rt.run(rid)["result"]["reply"]


def test_active_partial_reply_is_restored_by_session_snapshot(runtime, monkeypatch):
    rt, services, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *a: None)
    rid = rt.submit(pid, sid, "request", "hello")["run_id"]
    with rt.db() as conn, conn:
        conn.execute("UPDATE session_runs SET status='running' WHERE id=?", (rid,))
    rt.emit(sid, rid, "assistant.start", {})
    rt.emit(sid, rid, "assistant.delta", {"text": "partial reply"})
    other = services.create_chat_session(pid, "Other")["id"]
    assert rt.snapshot(pid, sid)["live_text"] == "partial reply"
    assert rt.snapshot(pid, other)["live_text"] == ""


def test_archive_and_submit_cannot_both_commit(runtime, monkeypatch):
    from nl_coding_agent.app.chat_sessions import archive_session
    rt, services, pid, _ = runtime
    monkeypatch.setattr(rt, "start", lambda *a: None)
    for index in range(8):
        sid = services.create_chat_session(pid, str(index))["id"]
        barrier = threading.Barrier(2)
        def accept():
            barrier.wait()
            try:
                rt.submit(pid, sid, "request", "hello")
            except ValueError:
                pass
        def archive():
            barrier.wait()
            try:
                archive_session(sid)
            except ValueError:
                pass
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(accept), pool.submit(archive)]
            for future in futures:
                future.result()
        with rt.db() as conn:
            archived = conn.execute("SELECT archived_at FROM chat_sessions WHERE id=?", (sid,)).fetchone()[0]
            accepted = conn.execute("SELECT count(*) FROM session_runs WHERE session_id=?", (sid,)).fetchone()[0]
        assert not (archived and accepted)


def test_removed_request_is_not_resumable(runtime, monkeypatch):
    rt, _, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *a: None)
    rid = rt.submit(pid, sid, "request", "hello")["run_id"]
    rt.control(pid, sid, "remove", run_id=rid)
    with pytest.raises(ValueError, match="not resumable"):
        rt.control(pid, sid, "resume", run_id=rid)


def test_archived_session_cannot_resume(runtime, monkeypatch):
    from nl_coding_agent.app.chat_sessions import archive_session
    rt, _, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *a: None)
    rid = rt.submit(pid, sid, "request", "hello")["run_id"]
    rt.control(pid, sid, "stop", run_id=rid)
    archive_session(sid)
    with pytest.raises(ValueError, match="active conversation"):
        rt.control(pid, sid, "resume", run_id=rid)


def test_stop_during_provider_stream_is_cancelled_and_can_resume(runtime, monkeypatch):
    rt, services, pid, sid = runtime
    started = threading.Event()
    calls = []
    class Provider:
        provider_id = "test"
        def chat_turn_stream(self, model, messages, tools, **options):
            calls.append(model)
            if len(calls) == 1:
                options["on_delta"]("partial answer")
                started.set()
                while not options["cancelled"]():
                    time.sleep(.01)
                raise InterruptedError("stream stopped")
            return {"content": "resumed answer"}
    monkeypatch.setattr(services, "_resolve_chat_provider", lambda *a, **kw: (Provider(), "model", "test", ""))
    rid = rt.submit(pid, sid, "request", "Explain testing", model_spec="test/model")["run_id"]
    assert started.wait(5)
    rt.control(pid, sid, "stop", run_id=rid)
    stopped = wait_status(rt, rid, "cancelled")
    assert stopped["result"]["partial_reply"] == "partial answer"
    rt.control(pid, sid, "resume", run_id=rid)
    wait_status(rt, rid)
    assert len(calls) == 2
    assert len(rt.snapshot(pid, sid)["runs"]) == 1


def test_followup_mission_receives_prior_decisions_from_the_same_session(runtime, monkeypatch):
    from nl_coding_agent.persistence.missions import get_mission
    rt, services, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *a: None)
    services._append_chat_message(pid, "user", "La funzione concordata è src/calc.py:subtract; conserva add.", session_id=sid)
    other = services.create_chat_session(pid, "Other")["id"]
    services._append_chat_message(pid, "user", "UNRELATED-OTHER-SESSION", session_id=other)
    rid = rt.submit(pid, sid, "request", "Aggiungi i test per la funzione concordata", allow_coding=True)["run_id"]
    mid = rt.prepare_mission(rid, "Aggiungi i test per la funzione concordata")
    goal = get_mission(mid)["goal"]
    assert "src/calc.py:subtract" in goal and "conserva add" in goal
    assert "UNRELATED-OTHER-SESSION" not in goal


def test_status_question_uses_snapshot_while_another_turn_is_busy(runtime, monkeypatch):
    rt, _, pid, sid = runtime
    monkeypatch.setattr(rt, "start", lambda *a: None)
    rid = rt.submit(pid, sid, "request", "hello")["run_id"]
    with rt.db() as conn, conn:
        conn.execute("UPDATE session_runs SET status='running' WHERE id=?", (rid,))
    status = rt.submit(pid, sid, "status-request", "A che punto sei?")
    assert status["status"] == "completed"
    assert rt.run(status["run_id"])["result"]["source"] == "session_snapshot"
    assert "running" in rt.run(status["run_id"])["result"]["reply"]
