"""F3b debugger readiness: detection and explicit, fail-closed adapter sessions."""
from __future__ import annotations
import pytest

from nl_coding_agent.app import debug as dbg


class FakeAdapter:
    def __init__(self, fail=False):
        self.started = 0
        self.stopped = 0
        self.fail = fail

    def start(self, *, script=None, args=None):
        if self.fail:
            raise RuntimeError("adapter failed")
        self.started += 1
        return {"started": True, "script": script}

    def stop(self):
        self.stopped += 1
        return {"stopped": True}

    def status(self):
        return {"active": self.started > self.stopped}


def test_detection_and_fail_closed_without_debugger():
    manager = dbg.DebugManager(detector=lambda: {
        "debugpy": False, "pdb": False, "selected": None, "available": False,
        "dap": False, "message": "none"})
    status = manager.status()
    assert status["available"] is False and status["session_active"] is False
    with pytest.raises(dbg.DebugError) as caught:
        manager.start()
    assert caught.value.code == "debugger-unavailable"
    pdb_manager = dbg.DebugManager(detector=lambda: {
        "debugpy": False, "pdb": True, "selected": "pdb", "available": True,
        "dap": False, "message": ""})
    with pytest.raises(dbg.DebugError) as pdb_error:
        pdb_manager.start()
    assert pdb_error.value.code == "pdb-manual-only"


def test_explicit_injected_adapter_start_stop_and_active_guard():
    adapter = FakeAdapter()
    manager = dbg.DebugManager(detector=lambda: {
        "debugpy": True, "pdb": True, "selected": "debugpy", "available": True,
        "dap": True, "message": ""})
    result = manager.start(script="app.py", adapter=adapter)
    assert result["started"] is True and adapter.started == 1
    assert manager.status()["session_active"] is True
    with pytest.raises(dbg.DebugError) as active:
        manager.start(adapter=adapter)
    assert active.value.code == "session-active"
    assert manager.stop()["stopped"] is True and adapter.stopped == 1
    assert manager.status()["session_active"] is False


def test_adapter_start_failure_clears_session_and_is_fail_closed():
    manager = dbg.DebugManager(detector=lambda: {"available": True, "selected": "debugpy"})
    with pytest.raises(RuntimeError):
        manager.start(adapter=FakeAdapter(fail=True))
    assert manager.status()["session_active"] is False
