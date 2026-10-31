from __future__ import annotations


def test_resource_snapshot_is_bounded_and_observational():
    from nl_coding_agent.core import resource_monitor
    snapshot = resource_monitor.snapshot()
    assert snapshot["checked_at"] > 0
    assert isinstance(snapshot["ram"], dict)
    assert isinstance(snapshot["cpu"], dict)
    assert isinstance(snapshot["gpus"], list)
    assert isinstance(snapshot["loaded_models"], list)
    assert isinstance(snapshot["warnings"], list)
    for gpu in snapshot["gpus"]:
        assert gpu["total_mb"] > 0
        assert gpu["used_mb"] >= 0
        assert gpu["free_mb"] >= 0
