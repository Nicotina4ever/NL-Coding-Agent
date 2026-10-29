"""Independent regression verification of a staged candidate (SPEC-28 TestGate).

The candidate is copied into a disposable workspace and the project test suite is
executed twice with the real embedded interpreter:

* candidate suite: staged source + staged tests (must be green);
* oracle suite: staged source + baseline (pinned) tests (must be green).

Both suites must pass. The oracle defeats the class of incident where an agent
weakens or replaces tests to hide a regression. Nothing in the live project is
executed or modified here.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ORACLE_TESTS_DIR = "tests"
ORACLE_PINNED_FILES = ("pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini", "conftest.py")
ORACLE_PINNED_INPUTS = ("docs/NEXT_SELF_BUILD_MISSION.md",)
RUNNER_NAME = "_pytest_runner.py"
ENV_DROP = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE")
DEFAULT_TIMEOUT_S = 600
RESOLUTION_GUARD_EXIT = 86

RUNNER_SOURCE = '''"""Generated pytest runner: prove the suite runs against this copy."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))
# SELF_BUILD_GUARD

import pytest

raise SystemExit(pytest.main(sys.argv[1:]))
'''


class VerificationError(RuntimeError):
    """Infrastructure-level verification failure (never a pass)."""


@dataclass
class SuiteResult:
    suite: str
    command: list[str]
    cwd: str
    exit_code: int | None
    passed: bool
    timed_out: bool
    duration_s: float
    stdout_tail: str
    stderr_tail: str
    failures: list[str]
    junit_path: str | None
    error: str | None = None

    @property
    def infrastructure_failure(self) -> bool:
        # Only reported test/collection failures are candidates for source repair.
        return not self.passed and (
            self.timed_out or self.exit_code not in (0, 1, 2)
            or not self.failures
        )


@dataclass
class VerificationReport:
    passed: bool
    candidate: SuiteResult
    oracle: SuiteResult
    verify_dir: Path
    started_at: str
    finished_at: str
    oracle_overlay: list[str] = field(default_factory=list)
    error: str | None = None


def _decode(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    try:
        from nl_coding_agent.tools.shell import decode_output

        return decode_output(data)
    except Exception:
        return data.decode("utf-8", errors="replace")


def scrubbed_env(data_dir: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in ENV_DROP}
    env.update({
        "NL_DATA_DIR": str(Path(data_dir).resolve()),
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONHASHSEED": "0",
        "NO_COLOR": "1",
        "GIT_PAGER": "cat",
        "PAGER": "cat",
    })
    return env


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def prepare_copies(
    stage_workspace: Path, stage_dir: Path, baseline: dict[str, str]
) -> tuple[Path, Path, list[str]]:
    stage_workspace = Path(stage_workspace).resolve()
    stage_dir = Path(stage_dir).resolve()
    if not stage_workspace.is_dir():
        raise VerificationError("Stage workspace not found: " + str(stage_workspace))
    verify_dir = stage_dir / "verification"
    if verify_dir.exists():
        shutil.rmtree(verify_dir, ignore_errors=True)
    candidate = verify_dir / "candidate"
    oracle = verify_dir / "oracle"
    verify_dir.mkdir(parents=True)
    shutil.copytree(stage_workspace, candidate, symlinks=False)
    shutil.copytree(stage_workspace, oracle, symlinks=False)
    overlay_ops = overlay_oracle(oracle, baseline)
    for suite in ("candidate", "oracle"):
        (verify_dir / "data" / suite).mkdir(parents=True, exist_ok=True)
    (verify_dir / "evidence").mkdir(parents=True, exist_ok=True)
    runner = RUNNER_SOURCE
    # Pin harness selection to the baseline, never to agent-controlled staged files.
    if "nl_coding_agent/__init__.py" in baseline:
        runner = runner.replace("# SELF_BUILD_GUARD", '''import nl_coding_agent
package = Path(nl_coding_agent.__file__).resolve()
if not package.is_relative_to(root):
    print("FATAL: imported package outside verification copy: " + str(package), file=sys.stderr)
    raise SystemExit(86)
''')
    _write_text(candidate / RUNNER_NAME, runner)
    _write_text(oracle / RUNNER_NAME, runner)
    return candidate, oracle, overlay_ops


def overlay_oracle(copy_root: Path, baseline: dict[str, str]) -> list[str]:
    copy_root = Path(copy_root).resolve()
    ops: list[str] = []
    tests_dir = copy_root / ORACLE_TESTS_DIR
    if tests_dir.exists():
        shutil.rmtree(tests_dir)
        ops.append("removed candidate tests dir")
    restored = 0
    for rel, content in baseline.items():
        if rel == ORACLE_TESTS_DIR or rel.startswith(ORACLE_TESTS_DIR + "/"):
            _write_text(copy_root / rel, content)
            restored += 1
    if restored:
        ops.append("restored " + str(restored) + " baseline test file(s)")
    for rel in ORACLE_PINNED_FILES:
        target = copy_root / rel
        if rel in baseline:
            _write_text(target, baseline[rel])
            ops.append("pinned baseline " + rel)
        elif target.exists():
            target.unlink()
            ops.append("removed candidate-added " + rel)
    for rel in ORACLE_PINNED_INPUTS:
        if rel in baseline:
            _write_text(copy_root / rel, baseline[rel])
            ops.append("pinned mission input " + rel)
    for path in sorted(copy_root.rglob("conftest.py")):
        rel = path.relative_to(copy_root).as_posix()
        if rel == ORACLE_TESTS_DIR or rel.startswith(ORACLE_TESTS_DIR + "/"):
            continue
        if rel in baseline or rel in ORACLE_PINNED_FILES:
            continue
        path.unlink(missing_ok=True)
        ops.append("removed candidate-added " + rel)
    return ops


def parse_junit(junit_path: Path) -> tuple[int, int, list[str]]:
    path = Path(junit_path)
    if not path.is_file():
        return 0, 0, []
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return 0, 0, []
    tests = 0
    failed = 0
    failures: list[str] = []
    for case in root.iter("testcase"):
        tests += 1
        bad = list(case.findall("failure")) + list(case.findall("error"))
        if bad:
            failed += 1
            failures.append(
                str(case.get("classname") or "") + "::" + str(case.get("name") or "")
            )
    return tests, failed, failures


def run_suite(
    copy_root: Path,
    *,
    suite: str,
    python_executable: str,
    data_dir: Path,
    timeout_s: int,
    junit_path: Path,
) -> SuiteResult:
    copy_root = Path(copy_root).resolve()
    junit_path = Path(junit_path).resolve()
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        python_executable,
        str(copy_root / RUNNER_NAME),
        "-q",
        "-p",
        "no:cacheprovider",
        "--no-header",
        "--junitxml=" + str(junit_path),
        "tests",
    ]
    started = time.time()
    timed_out = False
    exit_code: int | None = None
    stdout = ""
    stderr = ""
    error: str | None = None
    try:
        proc = subprocess.run(
            command,
            cwd=str(copy_root),
            env=scrubbed_env(data_dir),
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
        exit_code = int(proc.returncode)
        stdout = _decode(proc.stdout)
        stderr = _decode(proc.stderr)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = _decode(exc.stdout)
        stderr = _decode(exc.stderr)
        error = "timeout after " + str(timeout_s) + "s"
    except Exception as exc:  # noqa: BLE001 - surfaced as an infrastructure error
        error = str(exc)
    duration = round(time.time() - started, 2)
    tests, failed, failures = parse_junit(junit_path)
    if not timed_out and error is None:
        if exit_code == RESOLUTION_GUARD_EXIT:
            error = "resolution guard: package imported outside the verification copy"
        elif not junit_path.is_file():
            error = "missing junit report (runner exit " + str(exit_code) + "): " + (stderr or stdout)[-2000:]
        elif tests == 0:
            error = "suite collected zero tests"
        elif failed:
            error = str(failed) + " failing test(s)"
    passed = bool(
        exit_code == 0
        and not timed_out
        and error is None
        and tests > 0
        and failed == 0
    )
    return SuiteResult(
        suite=suite,
        command=command,
        cwd=str(copy_root),
        exit_code=exit_code,
        passed=passed,
        timed_out=timed_out,
        duration_s=duration,
        stdout_tail=stdout[-8000:],
        stderr_tail=stderr[-8000:],
        failures=failures,
        junit_path=str(junit_path),
        error=error,
    )


def verify_candidate(
    stage_workspace: Path,
    stage_dir: Path,
    baseline: dict[str, str],
    *,
    python_executable: str | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    report_path: Path | None = None,
) -> VerificationReport:
    started_at = datetime.now().isoformat(timespec="seconds")
    python_executable = python_executable or sys.executable
    candidate, oracle, overlay_ops = prepare_copies(stage_workspace, stage_dir, baseline)
    verify_dir = Path(stage_dir).resolve() / "verification"
    evidence = verify_dir / "evidence"
    candidate_result = run_suite(
        candidate,
        suite="candidate",
        python_executable=python_executable,
        data_dir=verify_dir / "data" / "candidate",
        timeout_s=timeout_s,
        junit_path=evidence / "junit-candidate.xml",
    )
    if candidate_result.timed_out:
        oracle_result = SuiteResult(
            suite="oracle",
            command=[],
            cwd="",
            exit_code=None,
            passed=False,
            timed_out=True,
            duration_s=0.0,
            stdout_tail="",
            stderr_tail="",
            failures=[],
            junit_path=None,
            error="skipped: candidate suite timed out",
        )
    else:
        oracle_result = run_suite(
            oracle,
            suite="oracle",
            python_executable=python_executable,
            data_dir=verify_dir / "data" / "oracle",
            timeout_s=timeout_s,
            junit_path=evidence / "junit-oracle.xml",
        )
    passed = bool(candidate_result.passed and oracle_result.passed)
    error = None
    if not passed:
        parts = []
        if not candidate_result.passed:
            parts.append("candidate suite failed: " + str(candidate_result.error))
        if not oracle_result.passed:
            parts.append("oracle suite failed: " + str(oracle_result.error))
        error = "; ".join(parts)
    report = VerificationReport(
        passed=passed,
        candidate=candidate_result,
        oracle=oracle_result,
        verify_dir=verify_dir,
        started_at=started_at,
        finished_at=datetime.now().isoformat(timespec="seconds"),
        oracle_overlay=overlay_ops,
        error=error,
    )
    payload = report_to_dict(report)
    report_file = evidence / "report.json"
    report_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if report_path is not None:
        dest = Path(report_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def report_to_dict(report: VerificationReport) -> dict:
    def suite_dict(suite: SuiteResult) -> dict:
        return {
            "suite": suite.suite,
            "command": suite.command,
            "cwd": suite.cwd,
            "exit_code": suite.exit_code,
            "passed": suite.passed,
            "timed_out": suite.timed_out,
            "duration_s": suite.duration_s,
            "failures": suite.failures,
            "junit_path": suite.junit_path,
            "error": suite.error,
            "infrastructure_failure": suite.infrastructure_failure,
            "stdout_tail": suite.stdout_tail,
            "stderr_tail": suite.stderr_tail,
        }

    return {
        "passed": report.passed,
        "error": report.error,
        "candidate": suite_dict(report.candidate),
        "oracle": suite_dict(report.oracle),
        "verify_dir": str(report.verify_dir),
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "oracle_overlay": report.oracle_overlay,
    }


def cleanup_verification(verify_dir: Path, *, keep: bool = False) -> None:
    if keep:
        return
    path = Path(verify_dir)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
