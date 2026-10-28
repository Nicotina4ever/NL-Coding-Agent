r"""Opt-in, local-only, redacted diagnostic report generator for the private beta.

Purpose (NL-BP-161): let a beta tester produce a small diagnostic report that they can
review and then attach manually to a GitHub issue.

Privacy and safety contract (enforced by this module and by tests/test_diagnostic_report.py):

* opt-in only: the tool never runs automatically and never writes without an explicit
  --output (or --dry-run preview);
* local only: no network imports, no upload, no telemetry, no model inference, no mission
  or supervisor execution, no subprocess execution;
* read-only for the installation: reads only an allow-list of small metadata files
  (manifests, pyproject.toml, nl_agent.py, README.md) and the two config files; it never
  reads project source trees, never recurses into project folders and never opens the
  SQLite database;
* redacts API keys/tokens/secrets, private keys, URL credentials, cloud identifiers,
  usernames, the user home directory and personal absolute paths;
* bounded and deterministic: fixed allow-lists, at most 8 checksum files / 8 MiB each,
  no timestamps, sorted output, so repeated runs on unchanged inputs are byte-identical;
* database rows, project content/listings and model checkpoints are explicitly NOT
  collected, so there is nothing to leak from them.

Manual use (from the installation folder):

    python\python.exe scripts\diagnostic_report.py --dry-run
    python\python.exe scripts\diagnostic_report.py --output beta-diagnostic.md
    python\python.exe scripts\diagnostic_report.py --format json --output beta-diagnostic.json

The report is a local file. Nothing is transmitted by this tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sys
from importlib import metadata, util as importlib_util
from pathlib import Path

TOOL_NAME = "diagnostic_report.py"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = 1
REPORT_KIND = "nl-coding-agent-diagnostic-report"

REDACTED = "<redacted>"
HOME_MARK = "<home>"
PATH_MARK = "<path>"
USER_MARK = "<user>"

MAX_CHECKSUM_FILES = 8
MAX_CHECKSUM_BYTES = 8 * 1024 * 1024
MAX_ENV_VALUE_CHARS = 160

TICK3 = chr(96) * 3

CHECKSUM_CANDIDATES = (
    "release-manifest.json",
    "platform-manifest.json",
    "payload_manifest.json",
    "SHA256_MANIFEST.json",
    "pyproject.toml",
    "nl_agent.py",
    "README.md",
)
LAUNCHER_CANDIDATES = (
    "NL Coding Agent.bat",
    "Self-Build Mode.bat",
    "doctor.bat",
    "status.bat",
    "NL Coding Agent.sh",
    "NL Coding Agent.command",
)
CONFIG_CANDIDATES = ("config/models.yaml", "config/voicebridge.yaml")
CAPABILITY_MODULES = ("PySide6", "crewai", "psutil", "yaml", "pytest")
CAPABILITY_EXECUTABLES = ("ollama", "git", "nvidia-smi", "ffmpeg")
PACKAGE_ALLOWLIST = ("crewai", "crewai-core", "crewai-cli", "PySide6", "psutil", "PyYAML", "litellm", "pytest")
ENV_ALLOWLIST = (
    "NL_DATA_DIR",
    "NL_MODELS",
    "NL_DEVELOPER_MODEL",
    "NL_REVIEWER_MODEL",
    "NL_DEBUG_MODEL",
    "NL_SELFBUILD_REVIEWER_MODEL",
    "NL_SELFBUILD_MAX_MISSIONS",
    "QT_QPA_PLATFORM",
    "PYTHONUTF8",
    "PYTHONIOENCODING",
    "PYTHONNOUSERSITE",
    "PIP_CONFIG_FILE",
    "CUDA_VISIBLE_DEVICES",
    "OLLAMA_HOST",
    "LANG",
    "LC_ALL",
)
SECRET_ENV_MARKERS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "AUTH",
    "PRIVATE",
    "SESSION",
)
NOT_COLLECTED = (
    "Project source code and file listings",
    "Project documentation content",
    "SQLite database rows, schema or file content",
    "Chat transcripts, prompts or model output",
    "Model files or checkpoints",
    "User files outside the installation folder",
    "Environment variables outside the allow-list",
    "Hostname, username, OS user account identifiers",
)
REDACTED_CATEGORIES = (
    "API keys, tokens, passwords and bearer credentials",
    "Private key blocks",
    "URL-embedded credentials",
    "AWS ARNs, cloud account/subscription identifiers and GUID-like identifiers",
    "User home directory and the OS username",
    "Absolute file-system paths (Windows drive paths and POSIX user paths)",
)

_BS = chr(92)
_WINDOWS_ABS = re.compile(
    "[A-Za-z]:" + "[" + _BS + _BS + "/][^ ,;\t\n]+"
)
_POSIX_USER_ABS = re.compile(
    "(?<![-A-Za-z0-9_.])/(?:Users|home|root|mnt|opt|var|tmp|Applications|Library|Volumes)/[^ ,;\t\n]+"
)

SECRET_PATTERNS = (
    (
        re.compile("-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----.*?-----END [A-Z ]{0,40}PRIVATE KEY-----", re.DOTALL),
        REDACTED + "-private-key",
    ),
    (
        re.compile("(?i)sk-[A-Za-z0-9_-]{10,}"),
        REDACTED + "-api-key",
    ),
    (
        re.compile("(?i)(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
        REDACTED + "-token",
    ),
    (
        re.compile("AKIA[0-9A-Z]{16}"),
        REDACTED + "-aws-key",
    ),
    (
        re.compile("(?i)Bearer +[A-Za-z0-9._:-]{16,}"),
        "Bearer " + REDACTED,
    ),
    (
        re.compile("eyJ[A-Za-z0-9_-]{8,}[.][A-Za-z0-9_-]{8,}[.][A-Za-z0-9_-]{8,}"),
        REDACTED + "-jwt",
    ),
    (
        re.compile("(?i)(api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|password|passwd)[ ]*[:=][ ]*[^ ,;\t\n]+"),
        "<redacted-credential>",
    ),
    (
        re.compile("(?i)(https?://)[^/@ ]+@"),
        "URL " + REDACTED + " ",
    ),
    (
        re.compile("arn:aws:[A-Za-z0-9_./:-]+"),
        REDACTED + "-arn",
    ),
    (
        re.compile("(?i)(account|subscription|tenant|project)[_-]?(id|number)[ ]*[:=][ ]*[A-Za-z0-9-]{6,}"),
        "<redacted-cloud-id>",
    ),
    (
        re.compile("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"),
        REDACTED + "-guid",
    ),
)


def _username(home: Path | None) -> str:
    if home is None:
        return ""
    name = Path(home).name
    return name if len(name) >= 3 else ""


def _replace_home(text: str, home: Path | None) -> str:
    if home is None:
        return text
    home_text = str(Path(home))
    variants = {home_text, home_text.replace(_BS, "/"), home_text.replace("/", _BS)}
    for variant in sorted(variants, key=len, reverse=True):
        if not variant:
            continue
        text = re.sub(re.escape(variant), HOME_MARK, text, flags=re.IGNORECASE)
    return text


def _is_personal_absolute_path(value: str) -> bool:
    """True when the whole value is a personal absolute path (not prose)."""
    text = value.strip()
    if not text:
        return False
    if text.startswith(HOME_MARK):
        return True
    if len(text) >= 3 and text[0].isalpha() and text[1] == ":" and text[2] in (_BS, "/"):
        return True
    if text.startswith("/") and not text.startswith("//"):
        return True
    return False


def redact_text(value, home: Path | None = None) -> str:
    """Redact secrets, cloud identifiers, usernames and personal absolute paths."""
    text = "" if value is None else str(value)
    text = _replace_home(text, home)
    text = re.sub(re.escape(HOME_MARK) + "[^ ,;]*", HOME_MARK, text)
    if _is_personal_absolute_path(text):
        return HOME_MARK if text.strip().startswith(HOME_MARK) else PATH_MARK
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    username = _username(home)
    if username:
        text = re.sub(
            "(?<![A-Za-z0-9])" + re.escape(username) + "(?![A-Za-z0-9])",
            USER_MARK,
            text,
            flags=re.IGNORECASE,
        )
    text = _WINDOWS_ABS.sub(PATH_MARK, text)
    text = _POSIX_USER_ABS.sub(PATH_MARK, text)
    return text


def redact_value(value, home: Path | None = None):
    """Recursively redact every string in a JSON-compatible structure."""
    if isinstance(value, str):
        return redact_text(value, home)
    if isinstance(value, dict):
        return {str(key): redact_value(item, home) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item, home) for item in value]
    return value


def _read_text(path: Path, max_bytes: int = MAX_CHECKSUM_BYTES) -> str | None:
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > max_bytes:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _load_json(path: Path) -> dict | None:
    text = _read_text(path)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _load_yaml(path: Path) -> dict | None:
    text = _read_text(path)
    if text is None:
        return None
    try:
        import yaml
    except Exception:
        return None
    try:
        data = yaml.safe_load(text)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _app_version(root: Path) -> str:
    version_file = root / "nl_coding_agent" / "core" / "version.py"
    text = _read_text(version_file, max_bytes=64 * 1024)
    if text:
        match = re.search("APP_VERSION[ ]*=[ ]*[\"']([^\"']+)[\"']", text)
        if match:
            return match.group(1)
    pyproject = _read_text(root / "pyproject.toml", max_bytes=256 * 1024)
    if pyproject:
        match = re.search("(?m)^[ ]*version[ ]*=[ ]*[\"']([^\"']+)[\"']", pyproject)
        if match:
            return match.group(1)
    return "unknown"


def _install_method(root: Path) -> str:
    if (root / "release-manifest.json").is_file() or (root / "platform-manifest.json").is_file():
        return "release-candidate"
    if (root / "payload_manifest.json").is_file():
        return "portable-payload"
    if (root / "pyproject.toml").is_file():
        return "source-checkout"
    return "unknown"


def _platform_info() -> dict:
    return {
        "system": platform.system() or "unknown",
        "release": platform.release() or "unknown",
        "machine": platform.machine() or "unknown",
        "architecture": platform.architecture()[0],
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
    }


def _app_info(root: Path, home: Path | None) -> dict:
    launchers = [name for name in LAUNCHER_CANDIDATES if (root / name).is_file()]
    return {
        "version": redact_text(_app_version(root), home),
        "install_method": _install_method(root),
        "launchers_present": sorted(launchers),
        "entry_point_present": (root / "nl_agent.py").is_file(),
        "embedded_runtime_present": (root / "python").is_dir(),
    }


def _config_summary(root: Path, home: Path | None, environ=None) -> dict:
    source = os.environ if environ is None else environ
    models_path = root / CONFIG_CANDIDATES[0]
    voice_path = root / CONFIG_CANDIDATES[1]
    models_data = _load_yaml(models_path)
    voice_data = _load_yaml(voice_path)

    models: dict = {"present": models_path.is_file(), "parsed": models_data is not None}
    if isinstance(models_data, dict):
        roles = models_data.get("roles")
        role_rows = []
        if isinstance(roles, dict):
            for role_name in sorted(roles):
                role = roles[role_name]
                model = role.get("model") if isinstance(role, dict) else role
                role_rows.append({"role": str(role_name), "model": redact_text(model, home)})
        providers = models_data.get("providers")
        provider_rows = []
        if isinstance(providers, dict):
            for provider_name in sorted(providers):
                provider = providers[provider_name]
                if isinstance(provider, dict):
                    provider_rows.append({
                        "name": str(provider_name),
                        "enabled": bool(provider.get("enabled", False)),
                        "kind": redact_text(provider.get("kind", "unknown"), home),
                    })
        cloud = None
        if isinstance(roles, dict):
            cloud = roles.get("fallback_cloud")
        models["roles"] = role_rows
        models["providers"] = provider_rows
        models["cloud_fallback_configured"] = isinstance(cloud, dict) and bool(cloud.get("model"))
        models["cloud_fallback_enabled"] = isinstance(cloud, dict) and bool(cloud.get("enabled", False))

    voice: dict = {"present": voice_path.is_file(), "parsed": voice_data is not None}
    if isinstance(voice_data, dict):
        project = voice_data.get("project")
        if isinstance(project, dict):
            voice["project_name"] = redact_text(project.get("name", ""), home)
            voice["external_root_configured"] = bool(project.get("root"))
            paths = project.get("protected_paths")
            voice["protected_paths_count"] = len(paths) if isinstance(paths, list) else 0
            globs = project.get("docs_globs")
            voice["docs_globs_count"] = len(globs) if isinstance(globs, list) else 0

    return {
        "models": models,
        "voicebridge": voice,
        "custom_data_dir_configured": bool(source.get("NL_DATA_DIR")),
    }


def _release_summary(root: Path, home: Path | None) -> dict:
    summary: dict = {}
    release = _load_json(root / "release-manifest.json")
    if isinstance(release, dict):
        archive = release.get("archive")
        archive_summary = {}
        if isinstance(archive, dict):
            for key in ("name", "sha256", "size", "file_count"):
                if key in archive:
                    archive_summary[key] = redact_value(archive[key], home)
        summary["release_manifest"] = {
            "archive": archive_summary,
            "version": redact_text(release.get("version", ""), home) or None,
        }
    platform_manifest = _load_json(root / "platform-manifest.json")
    if isinstance(platform_manifest, dict):
        product = platform_manifest.get("product") or {}
        platforms = platform_manifest.get("platforms") or {}
        summary["platform_manifest"] = {
            "product_version": redact_value(product.get("version"), home),
            "channel": redact_text(product.get("channel", ""), home) or None,
            "platforms": sorted(platforms) if isinstance(platforms, dict) else [],
            "release_ready": bool(platform_manifest.get("release_ready")),
        }
    payload = _load_json(root / "payload_manifest.json")
    if isinstance(payload, dict):
        summary["payload_manifest"] = {
            "tree_sha256": redact_text(payload.get("tree_sha256", ""), home) or None,
            "file_count": payload.get("file_count"),
            "total_size": payload.get("total_size"),
        }
    return summary


def _checksums(root: Path, home: Path | None, max_files: int = MAX_CHECKSUM_FILES) -> dict:
    entries = []
    skipped = 0
    for name in CHECKSUM_CANDIDATES:
        if len(entries) >= max_files:
            skipped += 1
            continue
        path = root / name
        try:
            if not path.is_file():
                continue
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_CHECKSUM_BYTES:
            skipped += 1
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            skipped += 1
            continue
        entries.append({"path": name, "size": size, "sha256": digest})
    return {
        "files": entries,
        "files_hashed": len(entries),
        "files_skipped": skipped,
        "truncated": skipped > 0,
    }


def _packages(home: Path | None) -> list[dict]:
    rows = []
    for name in sorted(PACKAGE_ALLOWLIST):
        try:
            version = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
        rows.append({"name": name, "version": redact_text(version, home)})
    return rows


def _capabilities() -> dict:
    modules = {}
    for name in CAPABILITY_MODULES:
        try:
            modules[name] = importlib_util.find_spec(name) is not None
        except (ImportError, ValueError, AttributeError):
            modules[name] = False
    executables = {}
    for name in CAPABILITY_EXECUTABLES:
        executables[name] = shutil.which(name) is not None
    return {
        "modules_available": modules,
        "executables_on_path": executables,
        "probe_notes": [
            "Only import/metadata and executable-on-PATH presence checks are performed.",
            "No network request, model inference, GPU command, audio device test or mission run is executed.",
            "Clipboard, microphone, ASR/TTS, GPU and real-hardware behaviour stay MANUAL-PENDING.",
        ],
    }


def _database_summary(root: Path) -> dict:
    db = root / "data" / "nl_coding_agent.sqlite3"
    summary: dict = {"present": db.is_file()}
    if db.is_file():
        try:
            summary["size_bytes"] = db.stat().st_size
        except OSError:
            pass
    summary["content_collected"] = False
    summary["note"] = "Database file presence/size only; no rows, schema or content are read."
    return summary


def _environment(home: Path | None, environ=None) -> dict:
    source = os.environ if environ is None else environ
    rows = {}
    for name in sorted(ENV_ALLOWLIST):
        if any(marker in name.upper() for marker in SECRET_ENV_MARKERS):
            continue
        if name not in source:
            continue
        raw = str(source.get(name, ""))
        rows[name] = redact_text(raw[:MAX_ENV_VALUE_CHARS], home)
    return rows


def build_report(
    root=None,
    home=None,
    environ=None,
    max_checksum_files: int = MAX_CHECKSUM_FILES,
) -> dict:
    """Build the redacted, deterministic report dictionary for one installation root."""
    root_path = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[1]
    home_path = Path(home).resolve() if home is not None else None
    report = {
        "kind": REPORT_KIND,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION, "schema_version": SCHEMA_VERSION},
        "privacy": {
            "opt_in": True,
            "uploaded": False,
            "telemetry": False,
            "network_used": False,
            "local_only": True,
            "manual_attachment_only": True,
            "redacted": list(REDACTED_CATEGORIES),
            "not_collected": list(NOT_COLLECTED),
        },
        "platform": _platform_info(),
        "application": _app_info(root_path, home_path),
        "installation": {
            "root_relative": True,
            "checksums": _checksums(root_path, home_path, max_checksum_files),
            "release": _release_summary(root_path, home_path),
        },
        "packages": _packages(home_path),
        "configuration": _config_summary(root_path, home_path, environ),
        "capabilities": _capabilities(),
        "database": _database_summary(root_path),
        "environment": _environment(home_path, environ),
        "bounds": {
            "max_checksum_files": max_checksum_files,
            "max_checksum_bytes": MAX_CHECKSUM_BYTES,
            "max_env_value_chars": MAX_ENV_VALUE_CHARS,
            "deterministic": True,
        },
        "how_to_share": [
            "Review this file before sharing; you can delete any section you do not want to publish.",
            "Attach it manually to the GitHub issue only if you are comfortable with the content.",
            "This tool never uploads anything and collects no telemetry.",
        ],
    }
    return redact_value(report, home_path)


def render_json(report: dict) -> str:
    return json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + chr(10)


def _md_table(rows, headers) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def render_markdown(report: dict) -> str:
    platform_info = report.get("platform", {})
    app = report.get("application", {})
    privacy = report.get("privacy", {})
    install = report.get("installation", {})
    config = report.get("configuration", {})
    caps = report.get("capabilities", {})
    database = report.get("database", {})
    python_info = platform_info.get("python") or {}
    tool = report.get("tool") or {}
    lines = [
        "# NL Coding Agent - diagnostic report",
        "",
        "Opt-in local diagnostic report. Review it before attaching it to an issue: the tool never",
        "uploads anything and collects no telemetry. Secrets, credentials, usernames, personal paths,",
        "project content, database rows and cloud identifiers are redacted or not collected.",
        "",
        "## Summary",
        "",
    ]
    lines += _md_table(
        [
            ["Operating system", str(platform_info.get("system", "unknown")) + " " + str(platform_info.get("release", ""))],
            ["Architecture", str(platform_info.get("machine", "unknown")) + " (" + str(platform_info.get("architecture", "")) + ")"],
            ["Python", str(python_info.get("implementation", "")) + " " + str(python_info.get("version", ""))],
            ["Application version", app.get("version", "unknown")],
            ["Install method", app.get("install_method", "unknown")],
            ["Report tool", str(tool.get("name", "")) + " " + str(tool.get("version", ""))],
            ["Redaction applied", "yes" if privacy.get("redacted") else "no"],
            ["Uploaded / telemetry", str(bool(privacy.get("uploaded"))) + " / " + str(bool(privacy.get("telemetry")))],
        ],
        ["Field", "Value"],
    )
    lines += ["", "## Application and installation", ""]
    lines += _md_table(
        [
            ["Entry point present", app.get("entry_point_present")],
            ["Embedded runtime present", app.get("embedded_runtime_present")],
            ["Launchers present", ", ".join(app.get("launchers_present") or []) or "none detected"],
        ],
        ["Field", "Value"],
    )
    checksums = install.get("checksums") or {}
    lines += ["", "## Package checksums", ""]
    rows = [[item.get("path"), item.get("size"), item.get("sha256")] for item in checksums.get("files") or []]
    if rows:
        lines += _md_table(rows, ["File", "Size (bytes)", "SHA-256"])
    else:
        lines += ["No manifest or source files found in the installation root."]
    lines += ["", "Files hashed: " + str(checksums.get("files_hashed", 0))
              + "; skipped (bound): " + str(checksums.get("files_skipped", 0)) + "."]
    release = install.get("release") or {}
    if release:
        lines += ["", "### Release manifest summary", "", TICK3 + "json",
                  json.dumps(release, indent=2, sort_keys=True), TICK3]
    lines += ["", "## Installed packages", ""]
    package_rows = [[p.get("name"), p.get("version")] for p in report.get("packages") or []]
    if package_rows:
        lines += _md_table(package_rows, ["Package", "Version"])
    else:
        lines += ["Package metadata unavailable."]
    models = config.get("models") or {}
    voice = config.get("voicebridge") or {}
    lines += ["", "## Configuration summary (values redacted)", ""]
    lines += _md_table(
        [
            ["models.yaml present", models.get("present")],
            ["models.yaml parsed", models.get("parsed")],
            ["Configured roles", ", ".join(row.get("role", "") for row in models.get("roles") or []) or "none"],
            ["Providers", ", ".join(row.get("name", "") for row in models.get("providers") or []) or "none"],
            ["Cloud fallback configured / enabled", str(models.get("cloud_fallback_configured")) + " / " + str(models.get("cloud_fallback_enabled"))],
            ["voicebridge.yaml present", voice.get("present")],
            ["External project configured", voice.get("external_root_configured")],
            ["Custom data dir configured", config.get("custom_data_dir_configured")],
        ],
        ["Field", "Value"],
    )
    lines += ["", "## Capability probes", ""]
    lines += _md_table(
        [[name, "available" if available else "absent"]
         for name, available in sorted((caps.get("modules_available") or {}).items())],
        ["Python module", "Status"],
    )
    lines += [""]
    lines += _md_table(
        [[name, "on PATH" if present else "not found"]
         for name, present in sorted((caps.get("executables_on_path") or {}).items())],
        ["Executable", "Status"],
    )
    for note in caps.get("probe_notes") or []:
        lines.append("- " + str(note))
    lines += ["", "## Database", ""]
    lines += _md_table(
        [["Present", database.get("present")],
         ["Size (bytes)", database.get("size_bytes", "n/a")],
         ["Content collected", database.get("content_collected")]],
        ["Field", "Value"],
    )
    lines.append(str(database.get("note", "")))
    environment = report.get("environment") or {}
    lines += ["", "## Environment (allow-listed, redacted)", ""]
    if environment:
        lines += _md_table([[name, value] for name, value in sorted(environment.items())],
                           ["Variable", "Value"])
    else:
        lines += ["No allow-listed environment variables are set."]
    lines += ["", "## Not collected", ""]
    for item in privacy.get("not_collected") or []:
        lines.append("- " + str(item))
    lines += ["", "## How to share", ""]
    for item in report.get("how_to_share") or []:
        lines.append("- " + str(item))
    lines.append("")
    text = chr(10).join(lines)
    return redact_text(text) + chr(10)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Opt-in local-only redacted diagnostic report (never uploads).",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="print the redacted report to stdout and write nothing")
    parser.add_argument("--output", help="write the redacted report to this local file")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown",
                        help="report format for --dry-run/--output (default: markdown)")
    parser.add_argument("--root", help="installation root to inspect (default: repository containing this script)")
    parser.add_argument("--overwrite", action="store_true", help="allow overwriting an existing --output file")
    parser.add_argument("--max-checksum-files", type=int, default=MAX_CHECKSUM_FILES,
                        help="bound on hashed metadata files (default: 8)")
    return parser


def main(argv=None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.dry_run and args.output:
        parser.error("use either --dry-run or --output, not both")
    if not args.dry_run and not args.output:
        parser.error("this tool is opt-in: pass --dry-run to preview or --output FILE to write a report")
    if args.max_checksum_files < 1:
        parser.error("--max-checksum-files must be >= 1")
    root = Path(args.root).expanduser().resolve() if args.root else Path(__file__).resolve().parents[1]
    try:
        report = build_report(root=root, home=Path.home(), max_checksum_files=args.max_checksum_files)
    except OSError as exc:
        print("ERROR: could not build diagnostic report: " + str(exc), file=sys.stderr)
        return 1
    text = render_json(report) if args.format == "json" else render_markdown(report)
    if args.dry_run:
        sys.stdout.write(text)
        return 0
    output = Path(args.output).expanduser()
    if output.exists() and not args.overwrite:
        print("ERROR: output file exists; pass --overwrite to replace it: " + output.name, file=sys.stderr)
        return 1
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8", newline=chr(10))
    except OSError as exc:
        print("ERROR: could not write report: " + str(exc), file=sys.stderr)
        return 1
    print("Wrote " + output.name + ". Review it before attaching it to an issue; nothing was uploaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
