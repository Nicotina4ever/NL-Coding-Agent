"""Capture real Studio screenshots at multiple sizes/DPI scales (U2 evidence).

Default (no --capture) spawns one subprocess per target with QT_SCALE_FACTOR set,
then writes PNGs under docs/evidence/gui/. Each child launches the actual Studio
(default Qt platform, NOT offscreen), runs a bounded interaction sequence and
grabs the window. No network/model/mission is started (ollama probe stubbed).

Usage:
  python scripts/capture_gui_screenshots.py
  python scripts/capture_gui_screenshots.py --capture 1280x800 1.0 out.png
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "docs" / "evidence" / "gui"
TARGETS = (("1280x800", "1.0", "STUDIO_1280x800_DPI100.png"),
           ("1600x1000", "1.25", "STUDIO_1600x1000_DPI125.png"),
           ("1920x1080", "1.5", "STUDIO_1920x1080_DPI150.png"))


def _capture(size: str, dpi: str, output: str) -> int:
    sys.path.insert(0, str(REPO_ROOT))
    os.environ["QT_SCALE_FACTOR"] = str(dpi)
    os.environ["NL_DATA_DIR"] = tempfile.mkdtemp(prefix="nl-shot-data-")
    from PySide6.QtWidgets import QApplication
    from nl_coding_agent.app.services import AppServices
    from nl_coding_agent.gui.main_window import MainWindow
    from nl_coding_agent.gui.dialogs.open_project import OpenProjectDialog
    from nl_coding_agent.gui.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    services = AppServices()
    services.check_ollama = lambda: False
    window = MainWindow(services)
    width, height = (int(part) for part in size.lower().split("x"))
    window.resize(width, height)
    window.setMinimumSize(1100, 700)
    window.show()
    for _ in range(8):
        app.processEvents()
    evidence = {"size": size, "dpi": dpi, "output": output}
    try:
        # Interaction sequence: pages + open dialog + Settings Advanced + Inspector.
        for page in ("projects", "files", "tasks", "goals", "settings"):
            window._switch_page(page)
            for _ in range(2):
                app.processEvents()
        dialog = OpenProjectDialog(services, window)
        dialog.show()
        app.processEvents()
        evidence["open_dialog_title"] = dialog.windowTitle()
        dialog.close()
        window._switch_page("settings")
        app.processEvents()
        advanced_visible = window._settings_panel._advanced_group.isVisibleTo(window)
        evidence["settings_advanced_visible"] = bool(advanced_visible)
        window._inspector.show_project({"name": "Studio UX evidence",
                                        "root": "docs/evidence/gui",
                                        "opened_at": "capture", "last_used": "capture"},
                                       {"capture": "real Qt window", "dpi": dpi})
        window._inspector.show_mission({"id": 0, "title": "Screenshot interaction",
                                        "status": "idle", "review_verdict": "—",
                                        "resume_count": 0})
        window._switch_page("projects")
        window._projects_panel._list.clearSelection()
        evidence["self_build_absent"] = (
            "Self-Build (This Agent)" not in window._projects_panel._self_build_btn.text()
            and window._projects_panel._self_build_btn.objectName() == "subtleLinkButton")
        for _ in range(4):
            app.processEvents()
        window._inspector._diagnostics.expandAll()
        app.processEvents()
        png = window.grab()
        out_path = Path(output)
        if not out_path.is_absolute():
            out_path = REPO_ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        ok = png.save(str(out_path), "PNG")
        evidence.update({"saved": bool(ok), "pixel_size": [png.width(), png.height()],
                         "platform": app.platformName(),
                         "notes": "real Studio window grab; no human aesthetic sign-off"})
        print(json.dumps(evidence, indent=2))
        return 0 if ok else 1
    finally:
        try:
            window.close()
            app.processEvents()
        except Exception:
            pass
        try:
            services._db.close()
        except Exception:
            pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Capture real Studio screenshots")
    parser.add_argument("--capture", nargs=3, metavar=("SIZE", "DPI", "OUTPUT"),
                        default=None)
    args = parser.parse_args(argv)
    if args.capture:
        return _capture(*args.capture)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    failures = []
    payload = []
    for size, dpi, name in TARGETS:
        output = OUT_DIR / name
        env = dict(os.environ)
        env.pop("QT_QPA_PLATFORM", None)
        env.pop("QT_OPENGL", None)
        completed = subprocess.run(
            [sys.executable, str(Path(__file__)), "--capture", size, dpi, str(output)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=180)
        line = {"target": size, "dpi": dpi, "output": str(output),
                "returncode": completed.returncode,
                "stdout_tail": completed.stdout[-2000:],
                "stderr_tail": completed.stderr[-2000:]}
        try:
            line["metrics"] = json.loads(completed.stdout)
        except ValueError:
            pass
        payload.append(line)
        if completed.returncode != 0 or not output.is_file():
            failures.append(line)
    print(json.dumps({"targets": payload, "failures": len(failures)}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
