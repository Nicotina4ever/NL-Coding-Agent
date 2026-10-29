"""Cross-platform headless GUI smoke for CI (offscreen Qt; no model/network calls).

Exit codes: 0 = PASS, 1 = FAIL. Writes a JSON report into reports/ when asked.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _workspace_dock_has(name: str, window) -> bool:
    """A Terminal / Git / Problems panel must live inside a StudioWorkspace dock,
    never reparented into the IDE tab widget."""
    try:
        workspace = getattr(window, "_workspace", None)
        if workspace is None:
            return False
        return workspace.docks.get(name) is not None
    except Exception:
        return False


def run(report_dir: Path | None = None) -> dict:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    # Point Qt to a known font directory to silence QFontDatabase warnings.
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\\Windows\\Fonts")
    sys.path.insert(0, str(_repo_root()))
    data_dir = tempfile.TemporaryDirectory(prefix="nl-ci-gui-")
    os.environ["NL_DATA_DIR"] = str(Path(data_dir.name) / "data")
    report = {"status": "FAIL", "checks": [], "platform": sys.platform,
              "qt_platform": os.environ.get("QT_QPA_PLATFORM")}
    services = None
    window = None
    try:
        from nl_coding_agent.app.services import AppServices
        from nl_coding_agent.gui.main_window import MainWindow
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFontDatabase

        app = QApplication.instance() or QApplication([])
        # After the QApplication exists, ensure a system font is loaded to silence QFontDatabase warnings.
        try:
            arial_path = r"C:\\Windows\\Fonts\\arial.ttf"
            if os.path.exists(arial_path):
                QFontDatabase.addApplicationFont(arial_path)
        except Exception:
            pass
        # The smoke must not touch Ollama/network; the status prober is a local check only.
        services = AppServices()
        services.check_ollama = lambda: False
        window = MainWindow(services)
        window.show()
        for _ in range(3):
            app.processEvents()
        checks = {
            "app_services": services is not None,
            "main_window": window is not None,
            "stack_pages_11": window._stack.count() == 11,
            "chat_page": window._page_index.get("chat") == 7,
            "ide_page": window._page_index.get("ide") == 8,
            "research_page": window._page_index.get("research") == 9,
            "goals_page": window._page_index.get("goals") == 10,
            "goals_sections_8": window._goals_panel._tabs.count() == 8,
            "goals_tasks_controls": bool(window._goals_panel._task_table.accessibleName())
                                    and bool(window._goals_panel._workers_table.accessibleName()),
            "goals_approval_control": window._goals_panel._approve_plan_btn is not None
                                      and bool(window._goals_panel._approve_plan_btn.accessibleName()),
            "goals_actions": bool(window._goals_panel._verify_btn.accessibleName())
                              and bool(window._goals_panel._replan_btn.accessibleName())
                              and bool(window._goals_panel._complete_btn.accessibleName()),
# IDE tabs only hold the Editor (Terminal / Git / Problems live in StudioWorkspace docks).
"ide_tabs_editor_only": window._ide_tabs.count() == 1 and window._ide_tabs.widget(0) is window._editor_panel,
# Terminal / Git / Problems are managed by the dock-based StudioWorkspace, never reparented into IDE tabs.
"terminal_in_dock": _workspace_dock_has("terminal", window),
"git_in_dock": _workspace_dock_has("git", window),
"problems_in_dock": _workspace_dock_has("problems", window),
            "terminal_read_only": window._terminal_panel._output.isReadOnly(),
            "git_read_only": window._git_panel._diff.isReadOnly(),
            "command_palette_actions": len(window._command_palette_actions()) >= 5,
        }
        report["checks"] = [{"name": name, "ok": bool(ok)} for name, ok in checks.items()]
        report["status"] = "PASS" if all(checks.values()) else "FAIL"
    except Exception as exc:  # noqa: BLE001 - report and fail closed
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        try:
            if window is not None:
                window.close()
                app.processEvents()
        except Exception:
            pass
        try:
            if services is not None:
                services._db.close()
        except Exception:
            pass
        data_dir.cleanup()
    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "headless_gui_smoke.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Headless GUI smoke (offscreen)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args(argv)
    report = run(Path(args.report_dir).resolve() if args.report_dir else None)
    if args.json or args.report_dir:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("Headless GUI smoke: " + report["status"])
        for check in report.get("checks", []):
            print(("  OK   " if check["ok"] else "  FAIL ") + check["name"])
        if report.get("error"):
            print("ERROR: " + str(report["error"]))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
