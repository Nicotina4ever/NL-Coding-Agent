import pytest
from nl_coding_agent.persistence import database
from nl_coding_agent.models.capabilities import *


def test_capabilities_probe_measured_beats_declared_and_unknown_never_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    database.init_db().close()
    records = probe_capabilities("ollama", "m1", {
        "tool_calling": lambda: True,
        "structured_output": lambda: False,
        "vision": lambda: (_ for _ in ()).throw(RuntimeError("no vision")),
    }, backend_version="1", hardware_fingerprint="hw")
    record_capabilities(records + records_from_declared("ollama", "m1", ["audio"]))
    cs = load_capabilities("ollama", "m1")
    assert cs.supports("tool_calling") is True
    assert cs.supports("vision") is False
    assert cs.supports("audio") is False  # declared never satisfies
    assert cs.satisfies(("tool_calling", "audio")) == (False, ("audio",))
    assert cs.state("vision") == "unavailable"
    assert cs.state("audio") == "declared"
