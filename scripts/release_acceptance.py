"""Release-acceptance matrix runner and beta acceptance record tool (NL-BP-140/164/165).

Read-only over committed evidence; the only writes are explicitly requested matrix
outputs and validated beta acceptance records. No network, model, upload, push or
destructive action. CI evidence is never treated as real-hardware support.

Commands:
  matrix [--records-dir DIR] [--json-out PATH] [--markdown-out PATH] [--json]
  record --input FILE [--records-dir DIR] [--json]
  verify [--records-dir DIR] [--json]

States are exactly: verified, partial, MANUAL-PENDING. Hardware/native steps are
MANUAL-PENDING unless a tester record contains explicit per-step results.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DEFAULT_RECORDS_DIR = REPO_ROOT / "docs" / "evidence" / "beta_acceptance"
TARGETS = ("windows-x86_64", "windows-arm64", "linux-x86_64", "linux-aarch64",
           "macos-x86_64", "macos-arm64")
REQUIRED_STEPS = ("install", "startup", "cli", "gui", "clipboard", "mic",
                  "asr_tts", "gpu", "offline", "restart")
HARDWARE_STEPS = ("clipboard", "mic", "asr_tts", "gpu")
STEP_RESULTS = ("pass", "fail", "not-tested", "manual-pending")
INSTALL_PATH_TYPES = ("clean-custom", "clean-default", "upgrade", "portable")
STATES = ("verified", "partial", "MANUAL-PENDING")
SCHEMA_VERSION = "1.0"
_ALIAS_RE = re.compile(r"^[A-Za-z0-9._-]{2,40}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_WIN_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"'<>|]*")
_UNC_PATH_RE = re.compile(r"\\\\[^\\\s]+\\[^\s\"'<>|]*")
_POSIX_HOME_RE = re.compile(r"/(?:Users|home)/[^\s\"'<>|/]+[^\s\"'<>|]*")


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _redact(value):
    if isinstance(value, str):
        redacted = _WIN_PATH_RE.sub("<redacted-path>", value)
        redacted = _UNC_PATH_RE.sub("<redacted-path>", redacted)
        redacted = _POSIX_HOME_RE.sub("<redacted-path>", redacted)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    return value


def _normalise_result(value) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    return text


def _iso_timestamp(value) -> bool:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return parsed.tzinfo is not None


def _target_descriptor(target_id: str) -> dict:
    from installer import platform_targets
    resolved = platform_targets.resolve_target(str(target_id))
    return {"target_id": resolved, **platform_targets.target_descriptor(resolved)}


def validate_record(payload, *, expect_target: str | None = None) -> tuple[dict, list]:
    """Validate and redact one tester record; returns (record, errors)."""
    errors = []
    if not isinstance(payload, dict):
        return {}, ["record must be a JSON object"]
    record = _redact(dict(payload))
    if str(record.get("schema_version")) != SCHEMA_VERSION:
        errors.append("schema_version must be " + SCHEMA_VERSION)
    alias = str(record.get("tester_alias") or "").strip()
    if not _ALIAS_RE.match(alias):
        errors.append("tester_alias must be an alias (2-40 chars: letters/digits/._-), not a name/email")
    if not _iso_timestamp(record.get("timestamp")):
        errors.append("timestamp must be an ISO-8601 value with timezone")
    target_data = {}
    try:
        target_data = _target_descriptor(str(record.get("target_id") or ""))
    except Exception as exc:
        errors.append("target_id is not a canonical installer target: " + str(exc))
    if expect_target and target_data and target_data["target_id"] != expect_target:
        errors.append("target_id does not match the expected target " + expect_target)
    if target_data:
        os_value = str(record.get("os") or "").strip().lower()
        arch_value = str(record.get("arch") or "").strip().lower()
        expected_os = str(target_data.get("os") or "").lower()
        expected_arch = str(target_data.get("arch") or "").lower()
        if os_value != expected_os:
            errors.append("os mismatch: target requires " + expected_os)
        aliases = set(str(item).lower() for item in target_data.get("machine_aliases") or ())
        aliases.add(expected_arch)
        if arch_value not in aliases:
            errors.append("arch mismatch: target requires " + "/".join(sorted(aliases)))
    package = record.get("package")
    if not isinstance(package, dict):
        errors.append("package object with version and sha256 is required")
    else:
        if not str(package.get("version") or "").strip():
            errors.append("package.version is required")
        if not _SHA_RE.match(str(package.get("sha256") or "").strip().lower()):
            errors.append("package.sha256 must be a 64-character lowercase hex digest")
    if str(record.get("install_path_type") or "") not in INSTALL_PATH_TYPES:
        errors.append("install_path_type must be one of " + ", ".join(INSTALL_PATH_TYPES))
    if not isinstance(record.get("evidence_notes"), str):
        errors.append("evidence_notes string is required")
    steps = record.get("steps")
    if not isinstance(steps, dict):
        errors.append("steps object is required")
        steps = {}
    for step in REQUIRED_STEPS:
        entry = steps.get(step)
        if not isinstance(entry, dict):
            errors.append("missing step: " + step)
            continue
        result = _normalise_result(entry.get("result"))
        if result not in STEP_RESULTS:
            errors.append("invalid result for step " + step + ": " + repr(entry.get("result")))
            continue
        if step in HARDWARE_STEPS and result == "pass":
            note = str(entry.get("evidence_note") or "").strip()
            if len(note) < 3:
                errors.append("hardware step " + step
                              + " claims pass without an explicit evidence_note")
    claim = record.get("support_claimed") or record.get("hardware_verified")
    if claim:
        for step in HARDWARE_STEPS:
            entry = steps.get(step) or {}
            if _normalise_result(entry.get("result")) != "pass":
                errors.append("support/hardware claim requires an explicit pass result for "
                              + step)
    record["tester_alias"] = alias
    record["steps"] = {
        step: {
            "result": _normalise_result((steps.get(step) or {}).get("result")),
            "evidence_note": str((steps.get(step) or {}).get("evidence_note") or "").strip(),
        }
        for step in REQUIRED_STEPS
    }
    return record, errors


def record_state(record: dict) -> dict:
    steps = record.get("steps") or {}
    results = {step: _normalise_result(steps.get(step, {}).get("result"))
               for step in REQUIRED_STEPS}
    standard = ("install", "startup", "cli", "gui", "offline", "restart")
    hardware_ok = all(results.get(step) == "pass" for step in HARDWARE_STEPS)
    standard_ok = all(results.get(step) == "pass" for step in standard)
    if standard_ok and hardware_ok:
        state = "verified"
    elif any(results.get(step) == "pass" for step in standard):
        state = "partial"
    else:
        state = "MANUAL-PENDING"
    return {"state": state, "results": results,
            "hardware_verified": hardware_ok,
            "manual_pending_steps": [step for step in REQUIRED_STEPS
                                     if results.get(step) != "pass"]}


def load_records(records_dir: Path) -> tuple[list[dict], list[dict]]:
    records, invalid = [], []
    if not records_dir.is_dir():
        return records, invalid
    for path in sorted(records_dir.glob("*.json")):
        if path.name.startswith(("acceptance_matrix", "summary")):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            invalid.append({"file": path.name, "errors": ["invalid JSON: " + str(exc)]})
            continue
        record, errors = validate_record(payload)
        if errors:
            invalid.append({"file": path.name, "errors": errors})
        else:
            record["_file"] = path.name
            records.append(record)
    return records, invalid


def _evidence_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _requirement_rows(repo: Path) -> list[dict]:
    release = _evidence_text(repo / "docs" / "RELEASE_ACCEPTANCE.md")
    backlog = _evidence_text(repo / "docs" / "PRODUCT_BACKLOG.md")
    rows = []
    for requirement_id, title, source_id in (
        ("NL-BP-140", "Release acceptance matrix runner with recorded evidence and manual-pending labels", "NL-BP-140"),
        ("NL-BP-164", "Cross-platform release acceptance with MANUAL-PENDING clean-machine and real-hardware matrix", "NL-BP-164"),
        ("NL-BP-165", "Cross-platform CI artifact provenance and real-hardware beta acceptance evidence", "NL-BP-165"),
    ):
        state = "MANUAL-PENDING"
        evidence = []
        if requirement_id in release and "PARTIAL" in release:
            match = re.search(requirement_id + r"[^\n]*", release)
            if match:
                evidence.append("docs/RELEASE_ACCEPTANCE.md: " + match.group(0).strip()[:300])
                if "MANUAL-PENDING" in match.group(0):
                    state = "partial"
                elif "VERIFIED" in match.group(0):
                    state = "verified"
                else:
                    state = "partial"
        if not evidence and requirement_id == "NL-BP-140":
            match = re.search(r"### " + requirement_id + r".*?\n.*?Status:\*\* ([a-z]+)",
                              backlog, re.S)
            evidence.append("docs/PRODUCT_BACKLOG.md: " + requirement_id)
            state = "partial" if match and match.group(1) == "partial" else "MANUAL-PENDING"
        rows.append({"requirement_id": requirement_id, "title": title,
                     "state": state, "evidence": evidence or [
                         "no committed real-hardware acceptance record; MANUAL-PENDING"]})
    return rows


def _ci_evidence(repo: Path) -> dict:
    workflow = repo / ".github" / "workflows" / "ci.yml"
    docs = _evidence_text(repo / "docs" / "CI.md")
    configured = workflow.is_file()
    return {"configured": configured,
            "state": "partial" if configured else "MANUAL-PENDING",
            "note": ("CI workflow committed; results are headless/regression evidence and never "
                     "real-hardware support") if configured else "CI workflow not found"}


def _secrets_gate(repo: Path) -> dict:
    text = _evidence_text(repo / "docs" / "SECRETS_AUDIT.md")
    gate = "MANUAL-PENDING"
    match = re.search(r"Upload gate \| \**([A-Za-z_-]+)", text)
    if match:
        gate = match.group(1)
    blocking = re.search(r"blocking: (\d+)", text)
    return {"gate": gate, "blocking_findings": int(blocking.group(1)) if blocking else None,
            "state": "partial" if gate.startswith("CLEAR") else "MANUAL-PENDING",
            "note": "owner review/authorization remains required; audit must be re-run at HEAD"}


def build_matrix(repo: Path, records_dir: Path) -> dict:
    records, invalid = load_records(records_dir)
    by_target: dict[str, list[dict]] = {target: [] for target in TARGETS}
    for record in records:
        by_target.setdefault(str(record["target_id"]), []).append(record)
    targets = []
    for target_id in TARGETS:
        descriptor = _target_descriptor(target_id)
        target_records = by_target.get(target_id, [])
        states = [record_state(record) for record in target_records]
        if not target_records:
            state = "MANUAL-PENDING"
            hardware_verified = False
            missing = list(REQUIRED_STEPS)
        elif any(item["state"] == "verified" for item in states):
            state = "verified"
            hardware_verified = True
            missing = []
        elif any(item["state"] == "partial" for item in states):
            state = "partial"
            hardware_verified = any(item["hardware_verified"] for item in states)
            missing = sorted({step for item in states for step in item["manual_pending_steps"]})
        else:
            state = "MANUAL-PENDING"
            hardware_verified = False
            missing = sorted({step for item in states for step in item["manual_pending_steps"]})
        targets.append({
            "target_id": target_id,
            "display_name": str(descriptor.get("display_name") or target_id),
            "os": descriptor.get("os"), "arch": descriptor.get("arch"),
            "ci": _ci_evidence(repo),
            "acceptance": {
                "state": state,
                "hardware_verified": hardware_verified,
                "record_count": len(target_records),
                "records": [record["_file"] for record in target_records],
                "manual_pending_steps": missing,
                "note": ("No real-hardware acceptance record; MANUAL-PENDING."
                         if not target_records else
                         "Derived only from explicit tester record results; CI is not evidence."),
            },
        })
    matrix = {
        "schema_version": SCHEMA_VERSION,
        "generated_from": ["installer/platform_targets.py",
                           "docs/HARNESS_ACCEPTANCE.md",
                           "docs/RELEASE_ACCEPTANCE.md",
                           "docs/SECRETS_AUDIT.md",
                           ".github/workflows/ci.yml",
                           "docs/evidence/beta_acceptance/records"],
        "ci_support_claimed": False,
        "targets": targets,
        "requirements": _requirement_rows(repo),
        "gates": [
            _ci_evidence(repo),
            _secrets_gate(repo),
            {"gate": "real-hardware beta acceptance", "state": "MANUAL-PENDING",
             "note": "requires tester records with explicit per-step results; CI can never mark this verified"},
        ],
        "invalid_records": invalid,
        "summary": {
            "targets": len(targets),
            "verified": sum(1 for row in targets if row["acceptance"]["state"] == "verified"),
            "partial": sum(1 for row in targets if row["acceptance"]["state"] == "partial"),
            "manual_pending": sum(1 for row in targets if row["acceptance"]["state"] == "MANUAL-PENDING"),
            "invalid_records": len(invalid),
            "no_ci_hardware_claim": True,
        },
    }
    return matrix


def render_markdown(matrix: dict) -> str:
    lines = ["# Release acceptance matrix", ""]
    lines.append("Generated from committed evidence and validated tester records. "
                 "States: verified / partial / MANUAL-PENDING. CI is never hardware support.")
    lines += ["", "## Targets", "",
              "| Target | OS/arch | Acceptance | Hardware verified | CI (headless only) | Records | Pending steps |",
              "|---|---|---|---|---|---|---|"]
    for row in matrix["targets"]:
        acceptance = row["acceptance"]
        lines.append("| " + row["target_id"] + " | " + str(row["os"]) + "/" + str(row["arch"])
                     + " | " + acceptance["state"] + " | "
                     + ("yes" if acceptance["hardware_verified"] else "no") + " | "
                     + row["ci"]["state"] + " | " + str(acceptance["record_count"]) + " | "
                     + ", ".join(acceptance["manual_pending_steps"]) + " |")
    lines += ["", "## Requirements", "",
              "| Requirement | State | Evidence |", "|---|---|---|"]
    for row in matrix["requirements"]:
        lines.append("| " + row["requirement_id"] + " | " + row["state"] + " | "
                     + " / ".join(row["evidence"]) + " |")
    lines += ["", "## Gates", "", "| Gate | State | Note |", "|---|---|---|"]
    for gate in matrix["gates"]:
        label = gate.get("gate") or gate.get("gate_name") or "CI"
        lines.append("| " + str(label) + " | " + str(gate.get("state")) + " | "
                     + str(gate.get("note")) + " |")
    lines += ["", "## Summary", ""]
    summary = matrix["summary"]
    lines.append("- verified targets: " + str(summary["verified"]))
    lines.append("- partial targets: " + str(summary["partial"]))
    lines.append("- MANUAL-PENDING targets: " + str(summary["manual_pending"]))
    lines.append("- invalid records: " + str(summary["invalid_records"]))
    lines.append("- CI hardware support claimed: no")
    return "\n".join(lines) + "\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _record_filename(record: dict) -> str:
    stamp = re.sub(r"[^0-9]", "", str(record["timestamp"]))[:14] or "unknown"
    sha = str(record["package"]["sha256"])[:12]
    alias = re.sub(r"[^A-Za-z0-9._-]", "_", record["tester_alias"])[:20]
    return (str(record["target_id"]) + "__" + alias + "__" + sha + "__" + stamp
            + ".json")


def command_matrix(args) -> int:
    repo = Path(args.repo_root).resolve()
    records_dir = Path(args.records_dir).resolve() if args.records_dir else repo / "docs" / "evidence" / "beta_acceptance"
    matrix = build_matrix(repo, records_dir)
    if args.json_out:
        _write(Path(args.json_out).resolve(), json.dumps(matrix, indent=2, sort_keys=True) + "\n")
    if args.markdown_out:
        _write(Path(args.markdown_out).resolve(), render_markdown(matrix))
    if args.json:
        print(json.dumps(matrix, indent=2, sort_keys=True))
    else:
        print("Release acceptance matrix: " + str(matrix["summary"]))
        if matrix["invalid_records"]:
            print("INVALID RECORDS: " + str(len(matrix["invalid_records"])), file=sys.stderr)
            return 1
    return 1 if matrix["invalid_records"] else 0


def command_record(args) -> int:
    repo = Path(args.repo_root).resolve()
    records_dir = Path(args.records_dir).resolve() if args.records_dir else repo / "docs" / "evidence" / "beta_acceptance"
    source = Path(args.input).resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("ERROR: cannot read record input: " + str(exc), file=sys.stderr)
        return 2
    record, errors = validate_record(payload)
    if errors:
        print("Record rejected:", file=sys.stderr)
        for error in errors:
            print("  - " + error, file=sys.stderr)
        return 2
    name = _record_filename(record)
    # Never overwrite an existing record.
    index = 1
    target = records_dir / name
    while target.exists():
        target = records_dir / (name[:-5] + "-" + str(index) + ".json")
        index += 1
    record_out = dict(record)
    _write(target, json.dumps(record_out, indent=2, sort_keys=True) + "\n")
    summary = {"ok": True, "record": str(target.name), "target_id": record["target_id"],
               "state": record_state(record)["state"],
               "hardware_verified": record_state(record)["hardware_verified"]}
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print("Stored beta acceptance record: " + summary["record"])
        print("Target: " + summary["target_id"] + "  State: " + summary["state"])
    return 0


def command_verify(args) -> int:
    repo = Path(args.repo_root).resolve()
    records_dir = Path(args.records_dir).resolve() if args.records_dir else repo / "docs" / "evidence" / "beta_acceptance"
    records, invalid = load_records(records_dir)
    states = [record_state(record) for record in records]
    summary = {
        "ok": not invalid,
        "records_dir": str(records_dir.relative_to(repo)) if records_dir.is_relative_to(repo) else str(records_dir),
        "records": len(records),
        "verified": sum(1 for item in states if item["state"] == "verified"),
        "partial": sum(1 for item in states if item["state"] == "partial"),
        "manual_pending": sum(1 for item in states if item["state"] == "MANUAL-PENDING"),
        "invalid_records": invalid,
        "ci_support_claimed": False,
    }
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print("Beta acceptance verification: " + ("OK" if summary["ok"] else "FAILED"))
        print("Records: " + str(summary["records"]) + "  verified=" + str(summary["verified"])
              + " partial=" + str(summary["partial"])
              + " MANUAL-PENDING=" + str(summary["manual_pending"]))
        for item in invalid:
            print("  INVALID " + item["file"] + ": " + "; ".join(item["errors"]))
    return 0 if summary["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Release acceptance matrix and beta records")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)
    matrix = sub.add_parser("matrix", help="Generate JSON/Markdown acceptance matrix")
    matrix.add_argument("--records-dir", default=None)
    matrix.add_argument("--json-out", default=None)
    matrix.add_argument("--markdown-out", default=None)
    matrix.add_argument("--json", action="store_true")
    matrix.set_defaults(func=command_matrix)
    record = sub.add_parser("record", help="Validate and store one tester record")
    record.add_argument("--input", required=True)
    record.add_argument("--records-dir", default=None)
    record.add_argument("--json", action="store_true")
    record.set_defaults(func=command_record)
    verify = sub.add_parser("verify", help="Validate records and print summary")
    verify.add_argument("--records-dir", default=None)
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(func=command_verify)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
