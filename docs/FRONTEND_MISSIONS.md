# NL Coder — VS Code Chat + mission control (`frontend/` 0.3.0)

This document is the operator and verification guide for the mission surface. The completed chat
surface (model selection, attachments, editor context, authorized URL research, persisted history) is
documented in [FRONTEND_CHAT.md](FRONTEND_CHAT.md); both complement
[FRONTEND_ARCHITECTURE.md](FRONTEND_ARCHITECTURE.md).

The extension remains a thin client. Missions are created, scheduled, staged, verified, reviewed and
promoted by the existing Python engine (`AppServices` + `Supervisor` + orchestrator + SQLite). The
extension never writes mission rows, staging manifests, permissions or model configuration, and never
implements a second orchestrator.

## What the extension exposes

| Requirement | Implementation |
|---|---|
| Real model selection and existing settings | Chat-model selector; mission developer/reviewer selectors; **Engine** tab fed by the read-only `engine_settings` tool (model config, providers, roles, chat default, agent roles, permissions, runtime paths, mission route defaults). Mission detail shows the persisted ModelRouter role bindings and per-attempt model/usage/duration evidence. Optional live probe uses the existing Model Hub (`GET /api/tags`, `/api/ps`), never loads a model. |
| Proportional team composition | The existing `_plan_tasks` planner always requires developer/tester/reviewer and adds a **read-only architect** for multi-file or design objectives, and a **read-only auditor** for security/audit objectives. Both pipelines use one shared analysis executor; the architect notes are passed into the developer prompt. Single-file missions keep the three-role team. |
| Start missions from Chat | Chat composer **Mission** mode and `/mission <objective>` shortcut, plus **NL Coding Agent: Start Mission…** command. Both call the existing `start_mission` MCP tool with exact provider/model routes. |
| Progress, agents, tool activity | Polled `mission_detail` shows status, progress bar, task rows (agent role/status/attempts), handoffs (`from → to`, summaries, payloads) and a **Tool activity (persisted evidence only)** section listing recorded write actions and the verification commands actually executed, plus task attempts (model output/error). The engine persists **no raw per-call tool telemetry**; no calls are invented. |
| Stop / resume / list persistent missions | **Missions** tab lists persisted rows; Stop calls `cancel_mission` (cooperative safe checkpoint); Resume calls `start_mission(resume_mission_id=…)` with the identical persisted goal; Open loads detail and diff. |
| Diffs, candidate/oracle tests, reviewer verdict | `candidate_diff` is rendered as a unified diff with `ok:false` shown honestly. `mission_detail.verification_runs` shows candidate/oracle commands, exit codes, pass/fail and bounded stdout/stderr. Reviewer verdict/review notes and promotion status are shown from persisted data. |
| Permissions and confirmations | Engine starts read-only by default; `nlCodingAgent.allowExecution` is an opt-in modal warning that restarts the server with `--allow-execution`. Every mission start/stop/resume has its own modal confirmation. Effective READ/WRITE/EXECUTE/DELETE/NETWORK/CLOUD policy is displayed read-only. |
| Correct project context | The workspace folder is passed as `--project`; the extension compares the announced project root with the open folder and refuses on mismatch. Changing folders restarts/rebinds. |

## Using it

1. Open a project folder in VS Code Insiders.
2. Run **NL Coding Agent: Start Chat** (or focus the NL view).
3. Optional: choose a chat model in the composer; **Engine** tab → **Probe models** refreshes the live
   local list. "Engine default" keeps the engine's own configured fallback.
4. To keep the engine read-only, do nothing. To allow missions, use **Engine → Enable execution** (or
   set `nlCodingAgent.allowExecution`) and accept the warning.
5. Switch the composer to **Mission**, choose developer/reviewer routes and describe a scoped change.
   Include explicit paths (e.g. `In src/calc.py add sub(a, b) … Change only src/calc.py.`) so the
   engine can scope the candidate. Confirm the modal.
6. Watch the mission banner (status/progress) and, in **Missions**, the tasks, handoffs, verification
   runs and diff. Stop and Resume are available when the engine reports the mission as
   `running/pending` or `interrupted/blocked/failed` respectively.
7. Completion is only `completed` after candidate+oracle verification and reviewer `APPROVE`; the live
   file is changed only after promotion. Rejections are `blocked` with the staged diff retained.

Commands contributed: **Start Chat**, **Start Mission…**, **Show Missions**, **Show Engine Settings**,
**Toggle Mission Execution**, **Show Backend Status**, **Reconnect Backend**.

## MCP surface used (no duplicates)

Existing/added tools: `project_context`, `engine_settings`, `nlc_converse`, `attachment_ingest`,
`chat_history`, `research_fetch_url`, `mission_list`, `mission_status`, `mission_events`,
`mission_detail`, `candidate_diff`, `start_mission`, `cancel_mission` (**13 tools**).

Read-only additions in `nl_coding_agent/app/mcp_engine.py`:

- `engine_settings(include_models=false, timeout_s=2.0)`: one projection of
  `get_model_config`, `get_model_config_path`, `discover_models`, `get_agent_roles`,
  `list_custom_agents`, `get_permissions`, `get_runtime_settings`, `is_cloud_escalation_enabled` and
  the existing mission default constants. It also reports `execution_enabled` and the **exact default
  mission routes**; role names are never passed to the engine as model routes.
- `mission_detail(mission_id)`: read-only projection of `AppServices.get_mission_details()`
  (mission row, tasks, attempts, handoffs, verification runs, progress, parsed `changed_paths`) with
  bounded strings.

Both reject foreign missions/read-denied projects like the existing read tools. Tests:
`tests/test_mcp_sdk.py::test_real_engine_stdio_readonly_project_binding` asserts presence and shape.

## Acceptance evidence

Isolated project fixture (`src/calc.py` with `add`; `tests/test_calc.py` imports `sub` so the baseline
test suite is red before the mission):

```python
def add(a, b):
    return a + b
```

```python
from src.calc import add, sub

def test_add():
    assert add(2, 3) == 5

def test_sub():
    assert sub(8, 3) == 5
    assert sub(2, 5) == -3
```

Goal: `In src/calc.py add sub(a, b) returning a - b. Preserve add and all existing tests. Change only
src/calc.py.` Routes: `ollama/qwen2.5-coder:7b-instruct-q4_K_M` for developer and reviewer (local,
already installed; the UI also offers `ollama/qwen3.5:9b` as the configured reviewer).

Verified results (logs and exported record in `docs/evidence/frontend/`):

- Mission #1: `completed`, verdict `APPROVE`, promotion `promoted`, `changed_paths=["src/calc.py"]`.
- Tasks: developer/tester/reviewer all `completed`; handoffs orchestrator→developer, developer→tester,
  tester→reviewer, reviewer→orchestrator and final orchestrator→user.
- Verification: `verify:candidate` PASS, `verify:oracle` PASS (`2 passed` each in the retained log),
  exit code 0.
- Live `src/calc.py` contains `def sub(a, b): return a - b`; retained diff:
  `1 file(s), +3/-0`.
- Proportional team acceptance (isolated two-file project): planner selected
  `architect -> developer -> tester -> reviewer`. All four tasks completed; the architect
  delivered read-only notes and token-usage metadata consumed by the developer; developer
  changed `src/calc.py` + `src/stats.py`; candidate and oracle suites both passed (2/2,
  exit 0); reviewer returned `APPROVE`; live files contain `sub` and `mean`; retained
  diff `2 file(s), +4/-2`; ModelRouter bindings and per-attempt model/usage metadata are
  visible in mission detail. The same path passed from the installed VSIX
  (`TEAM_MISSION_ACCEPTANCE_INSTALLED.log`), with the same retained diff.
  Evidence: `team-mission-evidence.json` and `TEAM_MISSION_ACCEPTANCE.log`.
- Dedicated stop/resume run: stop accepted → `interrupted` with the live tree untouched → resume →
  `completed`, `APPROVE`, `promoted`, `resume_count 1`.
- The same mission acceptance passes from the **installed VSIX payload** in an isolated Insiders
  profile (`VSIX_INSTALLED_MISSION_ACCEPTANCE.log`).

Reproduce:

```powershell
cd frontend
npm run compile
node test/runMissionTests.cjs          # dev extension host, isolated project
node test/runResumeTests.cjs           # stop -> interrupted -> resume
npm run package:vsix
node test/runInstalledVsixTests.cjs    # installs VSIX in isolated profile, mission from installed payload
node test/runChatFeatureTests.cjs      # real chat: model/attachment/editor/URL/history
node test/runInstalledChatFeatureTests.cjs  # same chat flows from the installed VSIX
```

## VSIX

- Package: `.workspace\dist\NL-Coding-Agent-0.3.0.vsix` (4,699,386 bytes; SHA-256
  `d5d0ad89413ad461755478fead7002b6a4cc568702973d3d9a6c1b2e850f8c7c`; includes the real product icon at
  `assets/icon.png`, display name **NL Coder**, runtime deps `@modelcontextprotocol/sdk` + `zod`,
  compiled `out/`, media).
- Normal local install: `code-insiders --install-extension .workspace\dist\NL-Coding-Agent-0.3.0.vsix`.
  The isolated acceptance used the official CLI wrapper
  (`…\Microsoft VS Code Insiders\bin\code-insiders.cmd`) with `--user-data-dir/--extensions-dir` so the
  default profile was not modified. (Direct `Code - Insiders.exe --install-extension` may be intercepted
  by an in-progress update; the wrapper is the reliable CLI path.)
- The extension ID is `nlcodingagent.nl-coding-agent`.
- Engine resolution when installed: set `nlCodingAgent.engineRoot` (or `NL_ENGINE_ROOT`); the installed
  extension cannot infer the repository path from its own folder.
- `nlCodingAgent.allowExecution` is a user setting; keep it `false` for a read-only assistant.
- URL fetch additionally needs owner-created `NETWORK` + `web-fetch` grants and
  `nlCodingAgent.researchProfile` set to `trusted-auto-review` to auto-approve (otherwise the backend
  reports `needs_approval`). The extension never grants permissions.

## Honest limits

- The engine does not persist per-tool-call telemetry. Handoff payload `actions` only covers writes made
  through the existing text-block fallback; native CrewAI tool calls are visible through their staged
  diff and `changed_paths`, not as an invocation log. The UI labels the available evidence and does not
  fabricate calls.
- Team composition is proportional but bounded by the current planner policy: developer/tester/reviewer
  are always required; architect/auditor are read-only additions. Multiple tasks per role and the
  CrewAI Flow pipeline are implemented but not active in the Chat path (Flow remains opt-in/sequential
  default). See [MULTI_AGENT_RUNTIME.md](MULTI_AGENT_RUNTIME.md).
- Reviewer judgment is nondeterministic; a REJECT is a legitimate `blocked` mission with its staged
  diff, verification and notes still available.
- Resume after an immediate stop can briefly show the stale `interrupted` row; the controller waits for
  the resumed run to start (`resume_count`/status transition) before declaring a terminal state.
- Legacy missions without `harness_version == 2` are listed but cannot run/resume.
- The standalone NL Code distribution still contains extension 0.1.0 and must be rebuilt to include this
  chat/mission UI. No standalone build was started for this increment.
