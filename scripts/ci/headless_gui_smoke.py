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


def run(report_dir: Path | None = None) -> dict:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
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

        app = QApplication.instance() or QApplication([])
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
            "stack_pages_10": window._stack.count() == 10,
            "chat_page": window._page_index.get("chat") == 7,
            "ide_page": window._page_index.get("ide") == 8,
            "research_page": window._page_index.get("research") == 9,
            "ide_tabs_4": window._ide_tabs.count() == 4,
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
