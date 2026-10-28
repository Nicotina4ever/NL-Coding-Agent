"""Application services facade — single interface for GUI and CLI."""
from __future__ import annotations

import json
import os
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from nl_coding_agent.persistence.database import db_path, init_db, log_event
from nl_coding_agent.projects.registry import (
    open_project as _open_project,
    list_recent as _list_recent,
    remove_project as _remove_project,
    get_project_facts as _get_project_facts,
)
from nl_coding_agent.models.ollama_registry import (
    check_ollama_reachable, list_models, list_loaded_models,
)
from nl_coding_agent.models.providers import ModelHub, build_providers
from nl_coding_agent.resources.scheduler import get_scheduler


APP_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODELS_CONFIG = APP_ROOT / "config" / "models.yaml"


@dataclass
class Event:
    source: str
    level: str
    message: str
    payload: dict | None = None


class EventBus:
    """Simple in-process pub/sub for structured events."""

    def __init__(self):
        self._subscribers: list[Callable[[Event], None]] = []
        self._lock = threading.Lock()

    def subscribe(self, fn: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers.append(fn)

    def unsubscribe(self, fn: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers = [s for s in self._subscribers if s is not fn]

    def emit(self, event: Event) -> None:
        with self._lock:
            subs = list(self._subscribers)
        for sub in subs:
            try:
                sub(event)
            except Exception:
                pass


# Global event bus
_bus = EventBus()


def get_event_bus() -> EventBus:
    return _bus


class AppServices:
    """Facade for all application-level operations."""

    def __init__(self):
        self._db = init_db()
        self._bus = _bus
        self._supervisor_services: dict[int, object] = {}
        self._supervisor_lock = threading.Lock()

    # --- Project ---

    def open_project(self, path: str | Path) -> dict:
        result = _open_project(path)
        self._bus.emit(Event(
            source="projects",
            level="info",
            message=f"Opened project: {result['name']}",
            payload={"project_id": result["id"], "root": result["root"]},
        ))
        log_event(self._db, f"Opened project: {result['name']}", source="app")
        return result

    def list_recent_projects(self, limit: int = 20) -> list[dict]:
        return _list_recent(limit)

    def remove_project(self, project_id: int) -> bool:
        ok = _remove_project(project_id)
        if ok:
            self._bus.emit(Event(
                source="projects", level="info",
                message=f"Removed project id={project_id}",
            ))
        return ok

    # ----------------------------------------------------- LSP/MCP/debug (F3b)
    def _lsp_manager(self, project_root):
        root = str(Path(project_root).resolve())
        managers = getattr(self, "_lsp_managers", None)
        if managers is None:
            managers = self._lsp_managers = {}
        if root not in managers:
            from nl_coding_agent.app.lsp import LspManager
            managers[root] = LspManager(Path(root))
        return managers[root]

    def lsp_catalog(self) -> list[dict]:
        from nl_coding_agent.app.lsp import detect_language_servers
        return [server.to_dict() for server in detect_language_servers()]

    def lsp_start(self, project_root, language: str) -> dict:
        return self._lsp_manager(project_root).start(language)

    def lsp_diagnostics(self, project_root, language: str) -> dict:
        return self._lsp_manager(project_root).diagnostics(language)

    def lsp_problems(self, project_root, language: str) -> list[dict]:
        rows = []
        diagnostics = self.lsp_diagnostics(project_root, language)
        for uri, items in diagnostics.items():
            for item in items:
                rows.append({"severity": "error" if int(item.get("severity") or 1) <= 2 else "warning",
                             "source": "lsp", "message": str(item.get("message") or ""),
                             "path": uri, "line": item.get("line")})
        return rows

    def mcp_servers(self) -> list[dict]:
        from nl_coding_agent.app.mcp import McpManager
        return McpManager(getattr(self, "_current_project_id", None)).servers()

    def mcp_tools(self, server_name: str) -> list[dict]:
        from nl_coding_agent.app.mcp import McpManager
        return McpManager(getattr(self, "_current_project_id", None)).list_tools(server_name)

    def mcp_invoke_tool(self, server_name: str, tool_name: str, arguments=None, *,
                        human_approved: bool = False) -> dict:
        from nl_coding_agent.app.mcp import McpManager
        return McpManager(getattr(self, "_current_project_id", None)).invoke_tool(
            server_name, tool_name, arguments or {}, human_approved=human_approved)

    def debug_status(self) -> dict:
        from nl_coding_agent.app.debug import DebugManager
        manager = getattr(self, "_debug_manager", None)
        if manager is None:
            manager = self._debug_manager = DebugManager()
        return manager.status()

    def debug_start(self, *, adapter=None, script=None) -> dict:
        from nl_coding_agent.app.debug import DebugManager
        manager = getattr(self, "_debug_manager", None)
        if manager is None:
            manager = self._debug_manager = DebugManager()
        return manager.start(script=script, adapter=adapter)

    def debug_stop(self) -> dict:
        manager = getattr(self, "_debug_manager", None)
        return manager.stop() if manager is not None else {"stopped": False}

    def get_project_facts(self, project_id: int) -> dict:
        return _get_project_facts(project_id)

    def get_project(self, project_id: int) -> dict | None:
        from nl_coding_agent.projects.registry import get_project
        return get_project(project_id)

    def read_project_file(self, project_root: str | Path, rel_path: str) -> str:
        from nl_coding_agent.tools.filesystem import scoped_read_file
        return scoped_read_file(project_root, rel_path)

    def list_project_dir(self, project_root: str | Path, rel_path: str = ".") -> list[str]:
        from nl_coding_agent.tools.filesystem import scoped_list_dir
        return scoped_list_dir(project_root, rel_path)

    # --- External tools (SPEC-25 / NL-BP-073) ---

    def list_external_tools(self, probe: bool = True) -> list[dict]:
        """Read-only external tool discovery for Settings -> Permissions & External Tools.

        Probes are fixed, bounded version commands or a health GET; no tool is
        installed, copied, modified or handed arbitrary arguments.
        """
        from nl_coding_agent.tools.registry import ToolRegistry
        return ToolRegistry().describe_all(probe=probe)

    # --- Ollama / Models ---

    def check_ollama(self) -> bool:
        return check_ollama_reachable(self.get_ollama_url())

    def list_models(self):
        return list_models(self.get_ollama_url())

    def list_loaded_models(self):
        return list_loaded_models(self.get_ollama_url())

    def discover_models(self, timeout: float = 5.0):
        providers = build_providers(self.get_model_config())
        return ModelHub(providers).discover(timeout=timeout)

    def unload_model(self, provider_id: str, name: str) -> bool:
        providers = build_providers(self.get_model_config())
        return ModelHub(providers).unload(provider_id, name)

    def get_model_config_path(self) -> Path:
        override = os.environ.get("NL_MODELS_CONFIG")
        return Path(override) if override else DEFAULT_MODELS_CONFIG

    def get_model_config(self) -> dict:
        try:
            import yaml
            with self.get_model_config_path().open("r", encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
        except Exception:
            return {}

    def get_database_path(self) -> Path:
        return db_path()

    def get_ollama_url(self) -> str:
        config = self.get_model_config()
        return str((config.get("ollama") or {}).get("base_url") or "http://127.0.0.1:11434")

    def is_cloud_escalation_enabled(self) -> bool:
        config = self.get_model_config()
        fallback = (config.get("roles") or {}).get("fallback_cloud") or {}
        return bool(fallback.get("enabled", False))

    def get_agent_roles(self) -> list[dict]:
        roles = self.get_model_config().get("roles") or {}

        def role_model(role: str) -> str:
            return str((roles.get(role) or {}).get("model") or "")

        developer_model = role_model("developer")
        debugger_model = role_model("debugger") or developer_model
        return [
            {"role": "architect", "model": role_model("architect"), "kind": "llm"},
            {"role": "developer", "model": developer_model, "kind": "llm"},
            {
                "role": "tester",
                "model": "Deterministic verification",
                "kind": "deterministic",
            },
            {
                "role": "debugger",
                "model": debugger_model,
                "kind": "llm",
                "note": "" if role_model("debugger") else "defaults to developer",
            },
            {"role": "reviewer", "model": role_model("reviewer"), "kind": "llm"},
        ]

    def get_runtime_settings(self, project_root: str | Path | None = None) -> dict:
        root = None
        if project_root:
            try:
                root = str(Path(project_root).resolve())
            except Exception:
                root = str(project_root)
        return {
            "project_root": root,
            "database_path": str(self.get_database_path().resolve()),
            "ollama_base_url": self.get_ollama_url(),
            "model_config_path": str(self.get_model_config_path().resolve()),
            "cloud_escalation_enabled": self.is_cloud_escalation_enabled(),
        }

    # --- Audit ---

    def create_mission(self, project_id: int | None, title: str, goal: str) -> int:
        from nl_coding_agent.persistence.missions import create_mission as _create_m
        m_id = _create_m(project_id, title, goal)
        self._bus.emit(Event(
            source="missions", level="info",
            message=f"Created mission #{m_id}: {title}",
            payload={"mission_id": m_id, "project_id": project_id},
        ))
        log_event(self._db, f"Created mission #{m_id}: {title}", source="missions")
        return m_id

    # ------------------------------------------------------- mission attachments
    def prepare_attachment_paths(self, project_id: int | None, paths,
                                 *, mission_id: int | None = None,
                                 source: str = "drop") -> dict:
        from nl_coding_agent.app import attachments
        return attachments.AttachmentStore().prepare_paths(
            paths, source=source, project_id=project_id, mission_id=mission_id)

    def prepare_attachment_text(self, project_id: int | None, text: str,
                                *, mission_id: int | None = None) -> dict:
        from nl_coding_agent.app import attachments
        return attachments.AttachmentStore().prepare_text(
            text, project_id=project_id, mission_id=mission_id)

    def prepare_attachment_clipboard_image(self, project_id: int | None,
                                           image_bytes: bytes,
                                           *, mission_id: int | None = None) -> dict:
        from nl_coding_agent.app import attachments
        return attachments.AttachmentStore().prepare_clipboard_image(
            image_bytes, project_id=project_id, mission_id=mission_id)

    def list_mission_attachments(self, *, mission_id: int | None = None,
                                 project_id: int | None = None) -> list[dict]:
        from nl_coding_agent.app import attachments
        return attachments.list_attachments(mission_id=mission_id,
                                            project_id=project_id)

    def attach_attachments_to_mission(self, mission_id: int,
                                      attachment_ids: list[int]) -> int:
        from nl_coding_agent.app import attachments
        return attachments.attach_to_mission(int(mission_id), attachment_ids)

    def delete_attachment(self, attachment_id: int) -> bool:
        from nl_coding_agent.app import attachments
        return attachments.delete_attachment(int(attachment_id))

    # ------------------------------------------------------------- speech (F2)
    def speech_manager(self):
        manager = getattr(self, "_speech_manager", None)
        if manager is None:
            from nl_coding_agent.app.speech import SpeechManager
            manager = SpeechManager()
            self._speech_manager = manager
        return manager

    def speech_status(self) -> dict:
        manager = self.speech_manager()
        return {"capabilities": manager.capabilities.to_dict(),
                "audio_backend": manager.audio_backend(),
                "audio_available": manager.audio_backend() is not None,
                "active_model": manager.active_model(),
                "tts": manager.tts_status(), "cloud_asr": False, "telemetry": False}

    def speech_catalog(self) -> dict:
        return self.speech_manager().catalog()

    def speech_install_plan(self, engine: str) -> dict:
        return self.speech_manager().install_plan(engine)

    def speech_switch_model(self, model_id: str) -> dict:
        return self.speech_manager().switch_model(model_id)

    def speech_unload_model(self) -> dict:
        return self.speech_manager().unload_model()

    def speech_devices(self) -> dict:
        return self.speech_manager().list_input_devices()

    def speech_start_recording(self, *, max_seconds: int = 60) -> dict:
        return self.speech_manager().start_recording(max_seconds=max_seconds)

    def speech_stop_recording(self, session_id: str) -> dict:
        return self.speech_manager().stop_recording(session_id)

    def speech_transcribe(self, wav_path: str, *, language: str | None = None) -> dict:
        return self.speech_manager().transcribe(wav_path, language=language)

    def speech_tts_status(self) -> dict:
        return self.speech_manager().tts_status()

    def speech_speak(self, text: str) -> dict:
        return self.speech_manager().speak(text)


    # ------------------------------------------------------- Studio IDE (F3a)
    _EDITABLE_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
                          ".ini", ".cfg", ".csv", ".log", ".js", ".ts", ".css",
                          ".html", ".xml", ".sql", ".sh", ".bat", ".ps1", ".c",
                          ".h", ".cpp", ".java", ".cs", ".go", ".rs", ".rb", ".vue"}
    _MAX_EDITOR_BYTES = 2 * 1024 * 1024

    @staticmethod
    def _resolve_project_rel(project_root, rel_path):
        from pathlib import Path
        root = Path(project_root).resolve()
        target = (root / str(rel_path or "")).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("Path escapes the open project: " + repr(rel_path)) from exc
        return root, target

    def load_editor_file(self, project_root, rel_path):
        import hashlib
        root, target = self._resolve_project_rel(project_root, rel_path)
        if not target.is_file():
            return {"rel_path": str(rel_path), "error": "File not found",
                    "error_code": "not-found", "read_only": True}
        size = target.stat().st_size
        read_only = target.suffix.lower() not in self._EDITABLE_SUFFIXES or size > self._MAX_EDITOR_BYTES
        reason = "" if not read_only else ("File type/size is read-only in the editor (preview only).")
        raw = target.read_bytes()
        if b"\x00" in raw[:4096]:
            read_only = True
            reason = "Binary content cannot be edited as text."
        content = ""
        for encoding in ("utf-8-sig", "utf-16", "latin-1"):
            try:
                content = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        return {"rel_path": target.relative_to(root).as_posix(), "content": content,
                "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": size,
                "read_only": read_only, "read_only_reason": reason,
                "suffix": target.suffix.lower()}

    def save_editor_file(self, project_root, rel_path, content, *, expected_sha256=None):
        import hashlib, json
        from nl_coding_agent.persistence import database
        root, target = self._resolve_project_rel(project_root, rel_path)
        if target.suffix.lower() not in self._EDITABLE_SUFFIXES:
            return {"ok": False, "error": "File type is read-only in the editor.",
                    "error_code": "read-only"}
        if not target.is_file():
            return {"ok": False, "error": "File not found", "error_code": "not-found"}
        current = hashlib.sha256(target.read_bytes()).hexdigest()
        if expected_sha256 and expected_sha256 != current:
            return {"ok": False, "error_code": "stale-content",
                    "error": "The file changed on disk. Reload before saving.", "sha256": current}
        data = str(content).encode("utf-8")
        if len(data) > self._MAX_EDITOR_BYTES:
            return {"ok": False, "error_code": "file-too-large"}
        target.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        try:
            database.log_event(self._db, "Saved editor file: " + str(rel_path),
                               source="editor", event_kind="file-save",
                               payload=json.dumps({"rel_path": str(rel_path), "sha256": digest}))
        except Exception:
            pass
        return {"ok": True, "sha256": digest, "size_bytes": len(data)}

    # --------------------------------------------------------- terminal policy
    _NETWORK_COMMANDS = {"curl", "wget", "ssh", "scp", "sftp", "ftp", "telnet",
                         "nc", "ncat", "ping", "tracert", "nslookup", "dig",
                         "invoke-webrequest", "invoke-restmethod", "iwr", "irm", "pip"}
    _DESTRUCTIVE_COMMANDS = {"rm", "del", "erase", "rmdir", "rd", "format", "mkfs",
                             "fdisk", "diskpart", "dd", "shutdown", "reboot", "taskkill",
                             "stop-process", "kill", "killall", "cipher", "takeown",
                             "icacls", "reg", "bcdedit", "schtasks", "wmic", "mklink",
                             "chmod", "chown", "sudo", "runas", "su"}
    _SHELL_COMMANDS = {"cmd", "powershell", "pwsh", "bash", "sh", "zsh", "fish", "csh"}
    _DESTRUCTIVE_GIT = {"reset", "clean", "rebase", "filter-branch", "checkout",
                        "restore", "branch", "tag", "worktree"}
    _SAFE_READ_GIT = {"status", "diff", "log", "show", "branch", "rev-parse"}
    _NETWORK_GIT = {"push", "fetch", "pull", "clone", "remote", "ls-remote", "submodule"}

    def terminal_policy(self, project_id, argv):
        from nl_coding_agent.core import permissions
        policy = permissions.get_policy(project_id)
        parts = [str(item) for item in (argv or []) if str(item or "").strip()]
        result = {"allowed": False, "argv": parts, "reason": "", "error_code": ""}
        if not parts:
            result.update(error_code="empty-command", reason="No command was provided.")
            return result
        if not policy.get(permissions.EXECUTE):
            result.update(error_code="execute-denied",
                          reason="The EXECUTE permission is not granted for this project.")
            return result
        command = parts[0].lower()
        if command in self._SHELL_COMMANDS or any(ch in " ".join(parts) for ch in ";|&$><"):
            result.update(error_code="shell-unsafe",
                          reason="Shell interpreters and shell metacharacters are not allowed.")
            return result
        if command in self._DESTRUCTIVE_COMMANDS:
            result.update(error_code="destructive-denied",
                          reason="Destructive command is denied by the terminal policy.")
            return result
        if command == "git" and len(parts) > 1:
            sub = parts[1].lower()
            if sub in self._DESTRUCTIVE_GIT:
                result.update(error_code="destructive-git-denied",
                              reason="Destructive git subcommand is denied.")
                return result
            if sub in self._NETWORK_GIT:
                if not policy.get(permissions.NETWORK):
                    result.update(error_code="network-denied",
                                  reason="Network command requires an explicit NETWORK grant "
                                         "(denied by default).")
                    return result
                result.update(error_code="network-explicit",
                              reason="This command requires NETWORK; an explicit grant is present.")
                return result
            if sub not in self._SAFE_READ_GIT and sub not in {"add", "commit"}:
                result.update(error_code="git-not-allowlisted",
                              reason="Only read-only/allowlisted git subcommands are permitted.")
                return result
        network = command in self._NETWORK_COMMANDS
        if network:
            if not policy.get(permissions.NETWORK):
                result.update(error_code="network-denied",
                              reason="Network command requires an explicit NETWORK grant "
                                     "(denied by default).")
                return result
            result.update(error_code="network-explicit",
                          reason="This command requires NETWORK; an explicit grant is present.")
        result.update(allowed=True, reason="allowed")
        return result

    def run_terminal_command(self, project_id, project_root, argv, *, cwd_rel=".",
                             timeout=30, runner=None):
        import json, shlex, subprocess
        from pathlib import Path
        from nl_coding_agent.persistence import database
        root = Path(project_root).resolve()
        parts = shlex.split(argv) if isinstance(argv, str) else [str(item) for item in (argv or [])]
        policy = self.terminal_policy(project_id, parts)
        cwd = (root / str(cwd_rel or ".")).resolve()
        try:
            cwd.relative_to(root)
        except ValueError:
            policy = {"allowed": False, "error_code": "cwd-escape",
                      "reason": "Working directory must stay inside the open project.",
                      "argv": parts}
        audit = {"argv": parts, "allowed": policy["allowed"], "project_id": project_id}
        if not policy["allowed"]:
            try:
                database.log_event(self._db, "Terminal command refused: " + " ".join(parts)[:500],
                                   source="terminal", level="warning",
                                   event_kind="terminal-refused",
                                   payload=json.dumps(audit, default=str))
            except Exception:
                pass
            return {"ok": False, "error_code": policy["error_code"], "error": policy["reason"],
                    "argv": parts, "stdout": "", "stderr": "", "exit_code": None,
                    "audited": True}
        try:
            database.log_event(self._db, "Terminal command started: " + " ".join(parts)[:500],
                               source="terminal", event_kind="terminal-start",
                               payload=json.dumps(audit, default=str))
        except Exception:
            pass
        try:
            if runner is not None:
                captured = runner(parts, cwd, timeout)
            else:
                captured = subprocess.run(parts, cwd=str(cwd), shell=False,
                                          capture_output=True, text=True, timeout=int(timeout),
                                          encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return {"ok": False, "error_code": "timeout", "error": "Command timed out.",
                    "argv": parts, "stdout": "", "stderr": "", "exit_code": None, "audited": True}
        except FileNotFoundError as exc:
            return {"ok": False, "error_code": "command-not-found", "error": str(exc),
                    "argv": parts, "stdout": "", "stderr": "", "exit_code": None, "audited": True}
        except Exception as exc:
            return {"ok": False, "error_code": "execution-failed", "error": str(exc),
                    "argv": parts, "stdout": "", "stderr": "", "exit_code": None, "audited": True}
        if isinstance(captured, dict):
            stdout = str(captured.get("stdout") or "")
            stderr = str(captured.get("stderr") or "")
            code = captured.get("returncode", captured.get("exit_code"))
        else:
            stdout, stderr = str(captured.stdout or ""), str(captured.stderr or "")
            code = captured.returncode
        limit = 100000
        try:
            database.log_event(self._db, "Terminal command finished (exit " + str(code) + "): "
                               + " ".join(parts)[:400], source="terminal",
                               event_kind="terminal-end",
                               payload=json.dumps({**audit, "exit_code": code}, default=str))
        except Exception:
            pass
        return {"ok": int(code or 0) == 0, "exit_code": code, "stdout": stdout[:limit],
                "stderr": stderr[:limit], "stdout_truncated": len(stdout) > limit,
                "stderr_truncated": len(stderr) > limit, "argv": parts, "audited": True}

    @staticmethod
    def _run_git_readonly(project_root, args):
        import subprocess
        from pathlib import Path
        root = Path(project_root).resolve()
        try:
            completed = subprocess.run(["git", "-C", str(root), *args],
                                       capture_output=True, text=True, timeout=20,
                                       encoding="utf-8", errors="replace", shell=False)
        except FileNotFoundError:
            return {"ok": False, "error_code": "git-not-installed",
                    "error": "git executable not found", "output": ""}
        except Exception as exc:
            return {"ok": False, "error_code": "git-failed", "error": str(exc), "output": ""}
        return {"ok": completed.returncode == 0, "output": completed.stdout or "",
                "error": completed.stderr.strip(),
                "error_code": None if completed.returncode == 0 else "git-error"}

    def git_status(self, project_root):
        branch = self._run_git_readonly(project_root, ["rev-parse", "--abbrev-ref", "HEAD"])
        status = self._run_git_readonly(project_root, ["status", "--porcelain=v1"])
        log = self._run_git_readonly(project_root, ["log", "-1", "--oneline"])
        if not status["ok"]:
            return {"ok": False, "error_code": status["error_code"],
                    "error": status["error"], "branch": None, "changes": []}
        changes = []
        for line in status["output"].splitlines():
            if line.strip():
                changes.append({"code": line[:2].strip() or "?", "path": line[3:]})
        return {"ok": True, "branch": branch["output"].strip() if branch["ok"] else None,
                "changes": changes, "last_commit": log["output"].strip() if log["ok"] else None}

    def git_diff(self, project_root, *, staged=False):
        args = ["diff", "--cached"] if staged else ["diff"]
        result = self._run_git_readonly(project_root, args)
        return {"ok": result["ok"], "diff": result["output"], "error": result.get("error") or ""}

    def git_log(self, project_root, *, limit=20):
        result = self._run_git_readonly(project_root,
                                        ["log", "--oneline", "--decorate", "-n", str(int(limit))])
        return {"ok": result["ok"], "log": result["output"], "error": result.get("error") or ""}

    def verification_problems(self, project_id=None):
        from nl_coding_agent.persistence import missions
        rows = []
        for mission in missions.list_missions(project_id)[:50]:
            mission_id = int(mission["id"])
            for run in missions.get_verification_runs(mission_id):
                if int(run.get("passed") or 0):
                    continue
                rows.append({"severity": "error", "source": "verification",
                             "mission_id": mission_id,
                             "message": str(run.get("command") or "verification failed")
                                        + " (exit " + str(run.get("exit_code")) + ")",
                             "created_at": run.get("created_at")})
        return rows

    def scan_project_problems(self, project_root, *, limit=50):
        import ast
        from pathlib import Path
        root = Path(project_root).resolve()
        findings = []
        py_files = sorted(path for path in root.rglob("*.py")
                          if ".git" not in path.parts and ".workspace" not in path.parts
                          and "build" not in path.parts
                          and "__pycache__" not in path.parts)[:200]
        for path in py_files:
            try:
                ast.parse(path.read_text(encoding="utf-8", errors="replace"),
                          filename=str(path))
            except SyntaxError as exc:
                findings.append({"severity": "error", "source": "scan",
                                 "message": "Syntax error in "
                                            + path.relative_to(root).as_posix()
                                            + ": " + str(exc.msg) + " (line "
                                            + str(exc.lineno) + ")",
                                 "path": path.relative_to(root).as_posix()})
            except OSError as exc:
                findings.append({"severity": "warning", "source": "scan",
                                 "message": "Unreadable file " + path.name + ": " + str(exc)})
            if len(findings) >= limit:
                break
        if not (root / "README.md").is_file():
            findings.append({"severity": "info", "source": "scan",
                             "message": "Project has no README.md; documentation discovery is limited."})
        return findings[:limit]

    def project_problems(self, project_id, project_root):
        verification = self.verification_problems(project_id)
        scan = self.scan_project_problems(project_root)
        problems = verification + scan
        return {"problems": problems,
                "counts": {"errors": sum(1 for row in problems
                                         if row.get("severity") == "error"),
                           "warnings": sum(1 for row in problems
                                           if row.get("severity") == "warning")}}

    def list_missions(self, project_id: int | None = None) -> list[dict]:
        from nl_coding_agent.persistence.missions import list_missions as _list_m
        return _list_m(project_id)

    def get_mission_details(self, mission_id: int) -> dict | None:
        from nl_coding_agent.persistence.missions import (
            get_mission, get_tasks, get_handoffs, get_verification_runs,
            get_task_attempts, mission_progress,
        )
        m = get_mission(mission_id)
        if not m:
            return None
        m["tasks"] = get_tasks(mission_id)
        m["handoffs"] = get_handoffs(mission_id)
        m["verification_runs"] = get_verification_runs(mission_id)
        m["attempts"] = get_task_attempts(mission_id)
        m["progress"] = mission_progress(mission_id)
        return m

    def next_roadmap_mission(self, project_root: str | Path) -> dict:
        from nl_coding_agent.core.roadmap import next_mission
        return next_mission(project_root)

    def run_mission(
        self,
        mission_id: int,
        project_root: str | Path,
        goal: str | None = None,
        on_done: Callable | None = None,
        developer_model: str | None = None,
        reviewer_model: str | None = None,
        debug_model: str | None = None,
        stop_after: str | None = None,
    ) -> str:
        """Schedule autonomous multi-agent mission execution on the sequential scheduler."""
        task_id = f"mission-{mission_id}"
        root = Path(project_root).resolve()

        def _do_mission():
            from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
            orch = MultiAgentOrchestrator(root)
            try:
                res = orch.run_mission(
                    mission_id=mission_id,
                    goal=goal,
                    developer_model=developer_model,
                    reviewer_model=reviewer_model,
                    debug_model=debug_model,
                    stop_after=stop_after,
                )
                if on_done:
                    on_done(res)
                return res
            except Exception as e:
                self._bus.emit(Event(
                    source="orchestrator", level="error",
                    message=f"Mission #{mission_id} failed: {e}",
                ))
                if on_done:
                    on_done({"status": "failed", "error": str(e)})
                raise

        scheduler = get_scheduler()
        scheduler.submit(task_id, _do_mission, label=f"Mission #{mission_id}: {goal[:30]}")
        return task_id

    # --- Persistent supervisor (stage 3) ---

    def _supervisor_service(self, project_id: int):
        from nl_coding_agent.app.supervisor_service import SupervisorService

        key = int(project_id)
        with self._supervisor_lock:
            service = self._supervisor_services.get(key)
            if service is not None:
                return service
            project = self.get_project(key)
            if not project:
                raise ValueError(f"Project {project_id} not found")
            service = SupervisorService(Path(project["root"]), key)
            self._supervisor_services[key] = service
            return service

    def supervisor_start(self, project_id: int, *, mode: str | None = None,
                         max_missions: int | None = None) -> dict:
        """Start the persistent supervisor in a background thread (non-blocking)."""
        return self._supervisor_service(project_id).start(
            mode=mode, max_missions=max_missions,
        )

    def supervisor_stop(self, project_id: int, *, reason: str = "") -> dict:
        with self._supervisor_lock:
            service = self._supervisor_services.get(int(project_id))
        if service is not None:
            return service.stop(reason=reason)
        return self._supervisor_command(project_id, "stop", reason=reason)

    def supervisor_pause(self, project_id: int) -> dict:
        with self._supervisor_lock:
            service = self._supervisor_services.get(int(project_id))
        if service is not None:
            return service.pause()
        return self._supervisor_command(project_id, "pause")

    def supervisor_resume(self, project_id: int) -> dict:
        with self._supervisor_lock:
            service = self._supervisor_services.get(int(project_id))
        if service is not None:
            return service.resume()
        return self._supervisor_command(project_id, "resume")

    def _supervisor_command(self, project_id: int, name: str, *,
                            reason: str = "") -> dict:
        project = self.get_project(int(project_id))
        if not project:
            return {"ok": False, "reason": "Project not found"}
        try:
            from nl_coding_agent.core.supervisor import supervisor_command

            return supervisor_command(
                Path(project["root"]), name, requested_by="app", reason=reason,
            )
        except Exception as exc:  # surfaced to the caller, never raised into Qt
            return {"ok": False, "error": str(exc)}

    def supervisor_status(self, project_id: int) -> dict:
        with self._supervisor_lock:
            service = self._supervisor_services.get(int(project_id))
        if service is not None:
            return service.status()
        project = self.get_project(int(project_id))
        if not project:
            return {"status": "idle", "error": "Project not found"}
        try:
            from nl_coding_agent.core.supervisor import supervisor_status

            return supervisor_status(Path(project["root"]), project_id=int(project_id))
        except Exception as exc:
            return {"status": "unknown", "error": str(exc)}

    def supervisor_preflight(self, project_id: int) -> dict:
        project = self.get_project(int(project_id))
        if not project:
            return {"ok": False, "blockers": ["Project not found"]}
        try:
            from nl_coding_agent.core.supervisor import Supervisor

            supervisor = Supervisor(Path(project["root"]), project_id=int(project_id))
            return supervisor.preflight().to_dict()
        except Exception as exc:
            return {"ok": False, "blockers": [str(exc)]}

    def supervisor_queue(self, project_id: int, *, limit: int = 50) -> list[dict]:
        try:
            from nl_coding_agent.persistence import supervisor_store

            return supervisor_store.list_queue(int(project_id), limit=int(limit))
        except Exception:
            return []

    def supervisor_approvals(self, project_id: int, *, status: str | None = None) -> list[dict]:
        try:
            from nl_coding_agent.persistence import supervisor_store
            return supervisor_store.list_approvals(int(project_id), status=status)
        except Exception:
            return []

    def supervisor_decide_approval(self, project_id: int, approval_id: int, *,
                                   approved: bool, reason: str = "",
                                   decided_by: str = "human") -> dict:
        from nl_coding_agent.core.supervisor import Supervisor
        from nl_coding_agent.projects.registry import get_project
        project = get_project(int(project_id))
        if not project:
            return {"ok": False, "error": "Project not found"}
        supervisor = Supervisor(Path(project["root"]), project_id=int(project_id))
        return supervisor.decide_approval(int(approval_id), approved=approved,
                                          decided_by=decided_by, reason=reason)

    def supervisor_flow_runs(self, project_id: int, *, limit: int = 20) -> list[dict]:
        """Read-only durable Flow run rows for one project (C4c)."""
        try:
            from nl_coding_agent.persistence import supervisor_store

            return supervisor_store.list_flow_runs(project_id=int(project_id))[: int(limit)]
        except Exception:
            return []

    def supervisor_flow_status(self, project_id: int, *, flow_id: str | None = None) -> dict:
        """Read-only Flow pipeline status: configured pipeline + runs (+ one state)."""
        pipeline = "sequential"
        try:
            from nl_coding_agent.persistence import database

            config = database.get_json_setting(
                "supervisor.project." + str(int(project_id))
            )
            pipeline = str(config.get("pipeline") or "sequential")
        except Exception:
            pipeline = "sequential"
        runs = self.supervisor_flow_runs(project_id)
        counts: dict[str, int] = {}
        for row in runs:
            state = str(row.get("status") or "")
            counts[state] = counts.get(state, 0) + 1
        payload: dict = {
            "pipeline": pipeline,
            "flow_runs": runs,
            "flow_counts": counts,
            "read_only": True,
        }
        if flow_id:
            payload["flow_id"] = str(flow_id)
            try:
                from nl_coding_agent.flows.persistence import AppFlowPersistence

                payload["state"] = AppFlowPersistence().load_state(str(flow_id))
            except Exception as exc:  # noqa: BLE001 - read-only best effort
                payload["state_error"] = str(exc)
        return payload

    def get_permissions(self, project_id: int | None = None) -> dict:
        """Read-only effective permission policy for the GUI/settings view."""
        try:
            from nl_coding_agent.core import permissions

            return {
                "scopes": list(permissions.SCOPES),
                "policy": permissions.get_policy(project_id),
                "cloud_escalation_enabled": self.is_cloud_escalation_enabled(),
            }
        except Exception as exc:
            return {"scopes": [], "policy": {}, "error": str(exc)}

    def shutdown_supervisors(self) -> None:
        with self._supervisor_lock:
            services = list(self._supervisor_services.values())
            self._supervisor_services.clear()
        for service in services:
            try:
                service.shutdown()
            except Exception:
                pass

    # --- Audit ---

    def run_audit(self, project_id: int, on_done: Callable | None = None) -> str:
        """
        Schedule an audit task. Returns the task_id.
        The audit reads the project facts and emits structured events.
        Does NOT modify the target project.
        """
        from nl_coding_agent.projects.registry import get_project

        project = get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        task_id = f"audit-{project_id}"
        root = Path(project["root"])

        def _do_audit():
            from nl_coding_agent.projects.scanner import scan_project
            self._bus.emit(Event(
                source="audit", level="info",
                message=f"Starting audit of {root.name}",
                payload={"project_id": project_id},
            ))
            try:
                facts = scan_project(root)
                summary = (
                    f"Audit complete: {facts['file_count']} files, "
                    f"primary language: {facts['primary_language']}, "
                    f"frameworks: {', '.join(facts['frameworks']) or 'none detected'}"
                )
                self._bus.emit(Event(
                    source="audit", level="info",
                    message=summary,
                    payload={"project_id": project_id, "facts": {
                        "file_count": facts["file_count"],
                        "primary_language": facts["primary_language"],
                        "frameworks": facts["frameworks"],
                        "top_build_files": facts["top_build_files"],
                    }},
                ))
                log_event(self._db, summary, source="audit")
                if on_done:
                    on_done({"status": "ok", "facts": facts})
                return facts
            except Exception as e:
                msg = f"Audit failed: {e}"
                self._bus.emit(Event(source="audit", level="error", message=msg))
                log_event(self._db, msg, source="audit", level="error")
                if on_done:
                    on_done({"status": "error", "error": str(e)})
                raise

        scheduler = get_scheduler()
        scheduler.submit(task_id, _do_audit, label=f"Audit: {root.name}")
        return task_id

    # --- Events ---

    def recent_events(self, limit: int = 200) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


# Singleton
_services: AppServices | None = None
_services_lock = threading.Lock()


def get_services() -> AppServices:
    global _services
    with _services_lock:
        if _services is None:
            _services = AppServices()
        return _services
