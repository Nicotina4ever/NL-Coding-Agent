"""ROOT REORG Phase B (.workspace consolidation) path-policy regression tests.

These tests pin the single configurable workspace path policy introduced by
shared task-45:

* generated build/dist/logs/temp/cache/state data lives under
  <repository>/.workspace (override: NL_WORKSPACE_DIR);
* python/ (embedded runtime) and data/ (live user data) stay at their
  historical repository-relative paths;
* the pre-reorg root locations (build/, dist/, logs/, temp/, cache/) no longer
  exist, so no consumer can silently write outside the policy;
* packaging tools exclude .workspace entirely.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl_coding_agent.core import workspace  # noqa: E402
from nl_coding_agent.persistence import database  # noqa: E402

LEGACY_ROOT_OUTPUTS = ("build", "dist", "logs", "temp", "cache")


@pytest.fixture()
def clean_workspace_env(monkeypatch):
    monkeypatch.delenv(workspace.WORKSPACE_ENV_VAR, raising=False)
    return monkeypatch


def test_default_workspace_root_is_app_root_dot_workspace(clean_workspace_env):
    assert workspace.workspace_root() == (workspace.APP_ROOT / ".workspace").resolve()
    assert workspace.workspace_root() == (REPO_ROOT / ".workspace").resolve()
    for name in workspace.WORKSPACE_CHILDREN:
        assert workspace.workspace_path(name) == workspace.workspace_root() / name


def test_workspace_root_env_override_absolute(clean_workspace_env, tmp_path):
    clean_workspace_env.setenv(workspace.WORKSPACE_ENV_VAR, str(tmp_path))
    assert workspace.workspace_root() == tmp_path.resolve()
    assert workspace.workspace_path("dist", "payload") == tmp_path.resolve() / "dist" / "payload"
    created = workspace.workspace_path("logs", create=True)
    assert created.is_dir()
    assert created == tmp_path.resolve() / "logs"


def test_workspace_root_env_override_relative_resolves_from_app_root(clean_workspace_env):
    clean_workspace_env.setenv(workspace.WORKSPACE_ENV_VAR, "build/ws-test")
    assert workspace.workspace_root() == (workspace.APP_ROOT / "build" / "ws-test").resolve()


def test_named_roots_match_workspace_children(clean_workspace_env):
    root = workspace.workspace_root()
    assert workspace.build_root() == root / "build"
    assert workspace.dist_root() == root / "dist"
    assert workspace.logs_root() == root / "logs"
    assert workspace.temp_root() == root / "temp"
    assert workspace.cache_root() == root / "cache"
    assert workspace.state_root() == root / "state"


MIGRATED = (REPO_ROOT / ".workspace").is_dir()


@pytest.mark.skipif(not MIGRATED, reason="repository checkout is not migrated to the .workspace layout")
def test_workspace_directory_exists_after_migration(clean_workspace_env):
    root = workspace.workspace_root()
    assert root.is_dir(), "run the task-45 migration before this regression test"
    for name in workspace.WORKSPACE_CHILDREN:
        assert (root / name).is_dir(), name


@pytest.mark.skipif(not MIGRATED, reason="repository checkout is not migrated to the .workspace layout")
def test_legacy_root_output_directories_are_gone(clean_workspace_env):
    present = [name for name in LEGACY_ROOT_OUTPUTS if (REPO_ROOT / name).exists()]
    assert present == [], "legacy root output directories must live under .workspace now"
    assert (REPO_ROOT / ".workspace").is_dir()


HAS_EMBEDDED_RUNTIME = (REPO_ROOT / "python" / "python.exe").is_file()


@pytest.mark.skipif(not HAS_EMBEDDED_RUNTIME,
                    reason="embedded runtime/data are not present in a source-only checkout (CI)")
def test_python_and_data_stay_outside_workspace(clean_workspace_env):
    assert (REPO_ROOT / "python" / "python.exe").is_file()
    assert (REPO_ROOT / "data").is_dir()
    assert database._DEFAULT_DATA_ROOT == REPO_ROOT / "data"
    assert not (workspace.workspace_root() / "python").exists()
    assert not (workspace.workspace_root() / "data").exists()
    original = __import__("os").environ.get("NL_DATA_DIR")
    try:
        __import__("os").environ.pop("NL_DATA_DIR", None)
        assert database.db_path() == database._DB_PATH
        assert database.db_path().parent.name == "data"
    finally:
        if original is not None:
            __import__("os").environ["NL_DATA_DIR"] = original


def test_cli_state_and_log_paths_use_workspace_policy(clean_workspace_env):
    from nl_coding_agent import cli
    from nl_coding_agent.core import selfbuild_runner

    assert not hasattr(cli, "STATE_ROOT"), "cli must not cache a root-level state path"
    assert not hasattr(cli, "LOG_ROOT"), "cli must not cache a root-level log path"
    root = workspace.workspace_root()
    assert cli.state_root() == root / "state"
    assert cli.logs_root() == root / "logs"
    assert selfbuild_runner.logs_root() == root / "logs"


def test_gitignore_ignores_entire_workspace(clean_workspace_env):
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines()}
    assert ".workspace/" in lines
    assert "python/" in lines
    assert "data/" in lines


def test_packaging_tools_exclude_workspace(clean_workspace_env):
    import scripts.build_release as build_release
    import scripts.stage_portable as stage_portable

    assert workspace.WORKSPACE_DIRNAME in build_release.EXCLUDED_ROOTS
    assert workspace.WORKSPACE_DIRNAME in stage_portable.EXCLUDED_ROOTS


def test_no_production_module_caches_legacy_root_paths():
    """Regression guard: no tracked module may build APP_ROOT/build|dist|logs|temp|cache."""
    legacy_constants = (
        'APP_ROOT / "build"',
        'APP_ROOT / "dist"',
        'APP_ROOT / "logs"',
        'APP_ROOT / "temp"',
        'APP_ROOT / "cache"',
    )
    offenders = []
    for path in sorted((REPO_ROOT / "nl_coding_agent").rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for marker in legacy_constants:
            if marker in text:
                offenders.append((path.relative_to(REPO_ROOT).as_posix(), marker))
    assert offenders == []
