"""Global access-mode policy tests.

The four GUI modes are the only authorization source. These tests cover the
mode -> scope/capability matrix, legacy profile migration, the retired grant
boundary and the compatibility shim used by older callers.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path))
    from nl_coding_agent.persistence import database

    database.init_db().close()
    return tmp_path


def _permissions():
    from nl_coding_agent.core import permissions

    return permissions


def _insert_legacy_profile(profile: str, project_id: int = 139) -> None:
    from nl_coding_agent.persistence import database

    database.set_json_setting(
        "access.profile." + str(project_id), {"profile": profile})


def test_scope_matrix_and_capabilities(data_dir):
    permissions = _permissions()

    permissions.set_access_mode("read-only")
    assert permissions.check_access(permissions.CAPABILITY_READ).allowed
    assert not permissions.check_access(permissions.CAPABILITY_WRITE).allowed
    assert not permissions.check_access(permissions.CAPABILITY_WEB_FETCH).allowed
    assert not permissions.check_access(permissions.CAPABILITY_DELETE).allowed

    permissions.set_access_mode("workspace-write")
    assert permissions.check_access(permissions.CAPABILITY_WRITE).allowed
    assert permissions.check_access(permissions.CAPABILITY_EXECUTE).allowed
    assert not permissions.check_access(permissions.CAPABILITY_WEB_FETCH).allowed
    assert not permissions.check_access(permissions.CAPABILITY_MODEL_INFERENCE_CLOUD).allowed
    assert not permissions.check_access(permissions.CAPABILITY_DELETE).allowed

    permissions.set_access_mode("auto-review")
    assert permissions.check_access(permissions.CAPABILITY_WEB_FETCH).allowed
    assert permissions.check_access(permissions.CAPABILITY_WEB_SEARCH).allowed
    assert permissions.check_access(permissions.CAPABILITY_MODEL_INFERENCE_CLOUD).allowed
    assert not permissions.check_access(permissions.CAPABILITY_DELETE).allowed

    permissions.set_access_mode("full-access")
    assert permissions.check_access(permissions.CAPABILITY_DELETE).allowed
    assert permissions.check_access(permissions.CAPABILITY_WEB_FETCH).allowed
    assert permissions.check_access(permissions.CAPABILITY_GIT_PUSH).allowed


def test_workspace_write_allows_mission_execution_but_not_os_delete(data_dir):
    permissions = _permissions()
    permissions.set_access_mode("workspace-write")

    permissions.require(permissions.EXECUTE, project_id=72)
    permissions.require(permissions.WRITE, project_id=72)

    with pytest.raises(permissions.PermissionDenied):
        permissions.require(permissions.DELETE, project_id=72)


def test_legacy_profile_is_migrated_only_until_mode_is_chosen(data_dir):
    permissions = _permissions()
    _insert_legacy_profile("auto-review", project_id=139)

    assert permissions.get_access_mode(persist=True) == "workspace-write"
    with permissions._connection() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key='access.mode'").fetchone()
    assert row is not None and row["value"] == "workspace-write"

    permissions.set_access_mode("workspace-write")
    _insert_legacy_profile("full-access", project_id=139)
    assert permissions.get_access_mode() == "workspace-write"
    assert permissions.get_access_mode(persist=True) == "workspace-write"


def test_per_scope_grants_are_refused_once_mode_exists(data_dir):
    permissions = _permissions()
    permissions.set_access_mode("auto-review")

    with pytest.raises(permissions.PermissionDenied):
        permissions.grant(permissions.NETWORK, project_id=72)
    with pytest.raises(permissions.PermissionDenied):
        permissions.revoke(permissions.WRITE, project_id=72)


def test_services_reject_retired_controls_and_share_mode(data_dir):
    from nl_coding_agent.app.services import AppServices
    permissions = _permissions()
    services = AppServices()
    try:
        assert services.get_permissions(6)["access_mode"] == "workspace-write"
        with pytest.raises(permissions.PermissionDenied):
            services.set_permission_scope("network", True, project_id=6)
        with pytest.raises(permissions.PermissionDenied):
            services.save_cloud_escalation(True)
        services.set_access_profile(6, "full-access")
        assert services.access_profile(72)["profile"] == "full-access"
        assert services.is_cloud_escalation_enabled()
    finally:
        services._db.close()


@pytest.mark.parametrize("mode", ["read-only", "workspace-write", "auto-review", "full-access"])
def test_all_boundaries_agree_and_ignore_legacy_grants(data_dir, mode):
    from nl_coding_agent.persistence import database
    from nl_coding_agent.core import auto_review
    p = _permissions()
    # Old grants must neither elevate Read Only nor constrain Full Access.
    database.set_json_setting("permissions.policy.global", {s: False for s in p.SCOPES})
    database.set_json_setting("permissions.policy.project.6", {s: True for s in p.SCOPES})
    p.set_access_mode(mode)
    for project_id in (6, 72):
        assert p.get_policy(project_id) == p.get_policy()
        for cap in p.CAPABILITIES:
            scope = {"kind": "mission", "value": "60", "project_id": project_id}
            a = p.check_access(cap, scope)
            b = p.check_capability(cap, scope)
            review = auto_review.evaluate_action(
                auto_review.ActionDescriptor(capability=cap, scope_kind="mission",
                    scope_value="60", context={"project_id": project_id}),
                "manual", controls={name: False for name in auto_review.CONTROLS})
            assert a.allowed == b.allowed == review.auto_approved, (mode, cap, review)
            assert not b.needs_approval


def test_corrupt_global_mode_does_not_reactivate_legacy_full_access(data_dir):
    from nl_coding_agent.persistence import database
    p = _permissions()
    _insert_legacy_profile("full-access", 6)
    database.set_setting("access.mode", "corrupt")
    assert p.get_access_mode() == "read-only"
    assert not p.check_capability("write").allowed


@pytest.mark.parametrize("mode,allowed", [("workspace-write", False), ("auto-review", True), ("full-access", True)])
def test_research_has_no_additional_manual_profile_approval(data_dir, mode, allowed):
    from nl_coding_agent.research.service import ResearchService
    p = _permissions()
    p.set_access_mode(mode)
    result, _ = ResearchService(profile="manual").authorize(
        "fetch_read", project_id=6, url="https://example.com")
    assert (result.outcome == "allowed") == allowed
    assert result.outcome != "needs_approval"


def test_existing_agent_tools_recheck_global_mode_before_effects(data_dir, tmp_path, monkeypatch):
    from nl_coding_agent.tools import crew_tools
    p = _permissions()
    root = tmp_path / "project"
    root.mkdir()
    file = root / "calc.py"
    file.write_text("value = 1\n")
    p.set_access_mode("workspace-write")
    tools = {tool.name: tool for tool in crew_tools.get_project_tools(root)}
    p.set_access_mode("read-only")
    assert "denied" in tools["write_file"].run(path="new.py", content="bad").lower()
    assert "denied" in tools["patch_file"].run(path="calc.py", target="1", replacement="2").lower()
    monkeypatch.setattr(crew_tools, "scoped_run_command", lambda *a, **kw: pytest.fail("revoked execution"))
    with pytest.raises(p.PermissionDenied):
        tools["run_tests"].run()
    with pytest.raises(p.PermissionDenied):
        tools["run_command"].run(command="python -m pytest")
    assert file.read_text() == "value = 1\n"
    assert not (root / "new.py").exists()
    p.set_access_mode("workspace-write")
    assert "Successfully" in tools["write_file"].run(path="new.py", content="ok")


def test_full_access_commands_do_not_require_allowlists(data_dir, tmp_path):
    import sys
    from nl_coding_agent.app.services import AppServices
    from nl_coding_agent.core import job_manager
    p = _permissions()
    p.set_access_mode("full-access")
    assert job_manager._check_argv([sys.executable, "-c", "print('ok')"], tmp_path)
    assert job_manager._check_argv(["pwsh", "-Command", "Get-Date"], tmp_path)
    services = AppServices()
    try:
        assert services.terminal_policy(6, ["custom-tool.exe", "--version"])["allowed"]
        result = services.run_terminal_command(6, tmp_path, ["custom-tool.exe"], cwd_rel="..",
            runner=lambda argv, cwd, timeout: {"stdout": "ok", "returncode": 0})
        assert result["ok"]
        p.set_access_mode("workspace-write")
        with pytest.raises(job_manager.JobError):
            job_manager._check_argv([sys.executable, "-c", "print('ok')"], tmp_path)
    finally:
        services._db.close()


def test_powershell_project_script_validation_uses_correct_argument_offset(data_dir, tmp_path):
    from nl_coding_agent.core import job_manager
    script = tmp_path / "build.ps1"
    script.write_text("Write-Output ok\n")
    assert job_manager._check_argv(["pwsh", "-NoProfile", "-File", str(script)], tmp_path)
    with pytest.raises(job_manager.JobError):
        job_manager._check_argv(["pwsh", "-File"], tmp_path)


def test_historical_capability_denies_and_allow_once_are_audit_only(data_dir):
    from nl_coding_agent.persistence import permissions_store
    p = _permissions()
    conn = permissions_store.connect()
    try:
        for decision in ("deny", "allow-once"):
            permissions_store.insert_grant(conn, capability="delete", scope_kind="project",
                scope_value="6", project_id=6, decision=decision, source="legacy",
                context={}, expires_at=None)
    finally:
        conn.close()
    p.set_access_mode("workspace-write")
    assert not p.check_capability("delete", context={"project_id": 6}).allowed
    p.set_access_mode("full-access")
    for _ in range(2):
        assert p.check_capability("delete", context={"project_id": 6}).allowed
    rows = p.list_capability_grants("delete")
    assert len(rows) == 2 and all(row["consumed_at"] is None for row in rows)
