import pytest
from nl_coding_agent.agents import crew_backend
from nl_coding_agent.agents.specs import CrewSpec, TaskSpec, MemoryPolicy, DelegationPolicy, get_role


def _crew(memory=None, delegation=None):
    spec = get_role("developer")
    return CrewSpec(crew_id="c", agents=(spec,), tasks=(TaskSpec(task_id="t", description_template="d", expected_output="e", agent_role_id="developer"),),
                    memory=memory or MemoryPolicy(), delegation=delegation or DelegationPolicy())


def test_memory_off_default_and_cloud_embedder_refused(monkeypatch):
    class FakeCrew:
        def __init__(self, **kw): self.kw = kw
    monkeypatch.setattr(crew_backend, "Crew", FakeCrew)
    created = crew_backend.build_crew(_crew(), [], [])
    assert created.kw["memory"] is False
    cloud = _crew(MemoryPolicy(enabled=True, storage_dir="data/mem", embedder="openai"))
    with pytest.raises(crew_backend.CrewRuntimeError):
        crew_backend.build_crew(cloud, [], [])
    local = MemoryPolicy(enabled=True, storage_dir="data/mem", embedder="local")
    assert crew_backend.validate_memory_policy(_crew(local))["enabled"] is True
    with pytest.raises(crew_backend.CrewRuntimeError):
        crew_backend.build_crew(_crew(local), [], [])


def test_delegation_write_roles_never_delegate_and_depth_bounded():
    assert get_role("developer").allow_delegation is False
    with pytest.raises(crew_backend.CrewRuntimeError):
        crew_backend._enforce_delegation(_crew(delegation=DelegationPolicy(allow=True, max_depth=1, allowlist=("developer",))))
