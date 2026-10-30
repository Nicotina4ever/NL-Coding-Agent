from pathlib import Path

from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator


def _orchestrator(root: Path):
    instance = MultiAgentOrchestrator.__new__(MultiAgentOrchestrator)
    instance.root = root
    return instance


def test_dependencies_are_ordered_before_consumers(tmp_path):
    (tmp_path / "catalog").mkdir()
    (tmp_path / "catalog" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "catalog" / "repository.py").write_text("class R: pass\n", encoding="utf-8")
    (tmp_path / "catalog" / "service.py").write_text(
        "from catalog.repository import R\n", encoding="utf-8")
    (tmp_path / "catalog" / "api.py").write_text(
        "from catalog.service import R\n", encoding="utf-8")
    ordered = _orchestrator(tmp_path)._order_source_paths_by_imports(
        ["catalog/api.py", "catalog/service.py", "catalog/repository.py"])
    assert ordered == ["catalog/repository.py", "catalog/service.py", "catalog/api.py"]


def test_missing_files_preserve_declared_order(tmp_path):
    ordered = _orchestrator(tmp_path)._order_source_paths_by_imports(
        ["catalog/reservation_repository.py", "catalog/reservation_service.py",
         "catalog/reservation_api.py"])
    assert ordered == [
        "catalog/reservation_repository.py",
        "catalog/reservation_service.py",
        "catalog/reservation_api.py",
    ]
