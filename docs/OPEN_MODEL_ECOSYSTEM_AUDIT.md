# Open Model & Provider Ecosystem - Capability Audit (read-only)

**Task:** shared task-69. **Date:** 2026-10-28 (Europe/Rome). **Repository:** `K:\AI\NL Coding Agent` at git HEAD `65f9932` (clean working tree before this task).
**Type:** read-only capability audit + queue-only backlog input. **No feature was implemented, no application code was modified, and no model, network or mission run was started.**
**Directive under audit:** Open Model & Provider Ecosystem - presets as conveniences, not restrictions (2026-10-28, queue only).

---

## 1. Executive summary

The application already has an **evidence-based multi-provider foundation** but it is **config-file-centric, closed in protocol support and read-only in the UI**:

- **Existing:** `OllamaProvider` and a generic `OpenAICompatibleProvider` class; `build_providers()` builds enabled providers from `config/models.yaml`; generic `GET <base_url>/models` discovery; `api_key_env` bearer headers; health/reachability, loaded-model state and Ollama unload; a dynamic Ollama registry (`/api/tags`, `/api/ps`, CLI fallback) that inherently lists community namespaces/tags from the daemon; a tested `ModelRouter` with override/project/role/fallback resolution, capability filters, permission gate, resource gate and mission model snapshots; an evidence-based capability registry with measured/declared/unknown/unavailable states and measured-wins semantics; a read-only Model Hub GUI (table/filter/refresh), read-only Settings paths and service APIs for discovery/unload/config paths.
- **Missing (the directive's genuine gaps):** first-class editable built-in presets; custom provider profiles with arbitrary auth/headers/protocol and import/export/reuse; always-available manual provider/model entry; an extensible adapter registry (the current provider `kind` set is a closed branch); automatic parameter suggestions and unrestricted expert/backend-specific parameters (only temperature is passed today); per-model and per-role profiles with context/reasoning/tool-calling/prompt-template settings and persisted project bindings; explicit capability-state presentation + optional benchmarks/profiling that warn rather than reject ordinary experimental use; flexible routing across local/external/embedding/multimodal backends with explanations and user override; full Model Hub provider/profile management GUI/CLI/API without hardcoded approved family/architecture/quantization/provider lists; and an end-to-end acceptance scenario.
- **Existing requirements retained unchanged:** NL-BP-008 (verified Model Hub core), NL-BP-009 (partial capability registry), NL-BP-010 (partial role->model mapping), NL-BP-036 (partial model lifecycle UI), NL-BP-068/069 (planned Advisor/Competence Index), NL-BP-183 (planned Competence Lab), NL-BP-208 (planned HF acquisition). The new requirements extend rather than rewrite them.

Ten genuine gaps were registered as planned **NL-BP-224..233** in new **program stage 9** after the dedupe mapping in section 5.

## 2. Method and evidence rules

- Static read-only inspection of `nl_coding_agent/models/**`, `gui/widgets/models_panel.py`, `gui/widgets/settings_panel.py`, `app/services.py`, `config/models.yaml`, `nl_coding_agent/cli.py`, tests and indexes; commands in section 8.
- Line references are to the current files at the audit HEAD.
- No provider was probed, no model loaded/inferred and no network request was made by this audit. Existing tests were inspected but not executed (they can touch local provider endpoints).

## 3. Existing capability evidence

### 3.1 Model Hub providers (`nl_coding_agent/models/providers.py`)

| Evidence | Finding |
|---|---|
| `providers.py:24-73` | `ModelInfo`, `ProviderSnapshot` (provider id/label/kind/base_url/reachable/models/loaded/error/elapsed) and `ModelHubSnapshot` aggregation/errors |
| `providers.py:80-84` | shared `_http_json()` using stdlib urllib (no third-party HTTP client) |
| `providers.py:87-162` | `OllamaProvider`: probe via `check_ollama_reachable` + `/api/tags` + `/api/ps`; loaded flags; error snapshots; `unload()` delegates to `ollama_stop_model` |
| `providers.py:165-254` | `OpenAICompatibleProvider`: `base_url`, optional `api_key_env`; `_headers()` builds **Bearer Authorization only when the env var is set**; probe GETs `{base_url}/models` and parses `data[].id/name`; HTTP/error snapshots; `unload()` is a no-op returning False |
| `providers.py:256-293` | `build_providers(config)`: reads `config["providers"]`; enabled entries only; `kind` branch is **closed**: `ollama` or `{"openai_compatible","openai","lm_studio","llama_cpp"}`; `base_url`; `api_key_env`; no custom headers/auth/protocol hooks |
| `providers.py:296-307` | `ModelHub.discover/unload` across configured providers |

### 3.2 Dynamic Ollama discovery (`nl_coding_agent/models/ollama_registry.py`)

| Evidence | Finding |
|---|---|
| `ollama_registry.py:12, 45-51` | loopback base URL `http://localhost:11434`; reachability via `/api/tags` |
| `ollama_registry.py:54-88` | model list via `/api/tags` (dynamic tags as returned by the daemon), with `ollama list` CLI fallback |
| `ollama_registry.py:91-114` | loaded models via `/api/ps` with `ollama ps` fallback |
| `ollama_registry.py:117-120` | `stop_model()` via CLI `ollama stop` |

**Note:** community namespaces/tags are displayed only if the Ollama daemon returns them; there is no namespace filtering, no manual namespace/model id entry UI and no namespace-aware error handling.

### 3.3 Router (`nl_coding_agent/models/model_router.py`)

| Evidence | Finding |
|---|---|
| `model_router.py:48-100` | immutable `ModelBinding` (role, provider_id, model_name, base_url, arbitrary params/capabilities/capability_sources, source, measured_at, config_sha256); `is_cloud` by model name or remote endpoint |
| `model_router.py:108-143` | resolution order: explicit override -> project override -> role config -> fallback chain |
| `model_router.py:145-168` | capability load per binding + resource gate (wait/block) |
| `model_router.py:170-218` | `resolve()`: capability filter via measured-only support; `permissions.assert_model_permitted` per candidate; refusals recorded; returns snapshot binding |
| `model_router.py:222-234` | `build_llm()`: repeats permission gate; builds CrewAI `LLM` with model, base_url and **only `temperature` from params** - all other params are dropped |
| `model_router.py:236-301` | `mission_model_snapshots` table + record/load snapshots |
| grep `ModelRouter(` in `nl_coding_agent/**` | **no instantiation in product code** - the router is a tested module but not yet wired into the live mission pipeline |

### 3.4 Capability registry (`nl_coding_agent/models/capabilities.py`)

| Evidence | Finding |
|---|---|
| `capabilities.py:1-7` | evidence-based: measured > declared > unknown; probes only on explicit human/CLI action; no telemetry |
| `capabilities.py:17-18` | `CAPABILITIES = (tool_calling, structured_output, vision, audio, context)`; `STATES = (measured, declared, unknown, unavailable)` |
| `capabilities.py:34-63` | additive `model_capabilities` SQLite table (provider/model/capability unique, backend version, evidence kind, probe id, measured_at, hardware fingerprint, context limit, latency, source) |
| `capabilities.py:107-118` | `state()` -> unknown if absent; `supports()` -> **only measured passes**; declared/unknown never satisfy |
| `capabilities.py:132-165` | upsert records; measured wins on conflict |
| `capabilities.py:205-246` | caller-supplied probes; missing probe -> unknown; probe error -> unavailable; result -> measured/unavailable |
| `capabilities.py:249-257` | declared records from model metadata |

**Gap:** the directive's declared/detected/tested/unknown presentation and "warn, do not arbitrarily reject experimental combinations" are not implemented - the router currently refuses any required capability that is not *measured* (capabilities.py:111-118, model_router.py:180-185).

### 3.5 GUI, Settings, services, CLI

| Evidence | Finding |
|---|---|
| `gui/widgets/models_panel.py:37-113` | read-only model table (Provider, Model, Size, Status, Family, Capabilities), provider filter, Refresh button, empty/error states |
| `gui/widgets/models_panel.py:185-288` | discovery off the GUI thread via `ModelHubFetchThread`; renders snapshot, hardware/speech/storage summaries; no edit/add/import/export/profile controls |
| `gui/widgets/settings_panel.py:59-81, 261-268` | read-only labels: Ollama base URL, model config path, cloud escalation; no provider editing |
| `app/services.py:197-236` | service API: check/list models, `discover_models()` builds providers from config, `unload_model()`, config path/dict getters (no save/update provider API) |
| `app/services.py:214-224` | config path from `NL_MODELS_CONFIG` env or fixed `config/models.yaml`; YAML read only |
| `cli.py:749, 770-772, 785-787, 805-807, 816-818` | CLI exposes only `--models <path>` and per-run `--dev-model/--reviewer-model/--debug-model` overrides; **no provider/profile management commands** |
| `config/models.yaml:6-25` | built-in config presets exist as YAML entries: `ollama` (enabled), `lm_studio` and `llama_cpp` (disabled, OpenAI-compatible kind, base URLs, api_key_env); edits require hand-editing YAML |
| `config/models.yaml:27-43` | role model/temperature entries + disabled `fallback_cloud`; no per-model profile, context/reasoning/tool-calling/prompt-template fields or project bindings |

### 3.6 Existing tests (inspected, not executed)

- `tests/test_model_hub.py` (7 tests): build-providers enabled entries, OpenAI-compatible probe parse/error, Ollama loaded models, hub aggregation/errors, panel render/error, sidebar presence.
- `tests/test_model_router.py` (1 integration test): resolution refusals/fallback/snapshot.
- `tests/test_model_capabilities.py` (1 test): measured beats declared; unknown never passes.
- `tests/test_crew_backend.py` (15 tests): role catalog/resolution and backend-level LLM construction.

### 3.7 Existing requirements retained unchanged

| ID | Status | Relevance |
|---|---|---|
| NL-BP-008 | verified | Multi-provider Model Hub core (discovery/health/loaded/unload) - retained as the provider-discovery foundation |
| NL-BP-009 | partial | capability registry from real probes - retained; 230 adds explicit state presentation/optional benchmarks |
| NL-BP-010 | partial | role->model mapping/overrides - retained; 229/231 add profiles/routing depth |
| NL-BP-036 | partial | model lifecycle UI - retained; 232 adds provider/profile management |
| NL-BP-068 | planned | Model Advisor (profiles/params) - retained; 228 consumes suggestions, 229 profiles |
| NL-BP-069 | planned | Competence Index/benchmarks - retained; 230/233 use optionally |
| NL-BP-183 | planned | Model Competence Lab - retained; 230 benchmark evidence may come from it |
| NL-BP-208 | planned | HF acquisition workflow - retained (model acquisition, not provider routing) |

## 4. Directive capabilities vs current state

| Directive capability | Exists today? | Comment |
|---|---|---|
| Built-in presets with editable defaults (Ollama, llama.cpp, LM Studio, OpenAI-compatible, extensible) | **Partial** | presets exist only as hand-edited YAML (config/models.yaml:6-25); not first-class/edit/import/export; no extensible preset list |
| Custom provider profiles (arbitrary URL/model/auth/headers/protocol, secret refs, import/export/reuse) | **No** | provider config is fixed YAML schema (kind/base_url/api_key_env); Bearer only; no headers/protocol/secret refs or profile store |
| Auto discovery + always-available manual entry | **Partial** | auto discovery exists for Ollama and OpenAI-compatible /models; no manual entry UI/API when discovery is unsupported or offline |
| Extensible protocol adapters, no closed provider list | **No** | kind branch closed to ollama/openai_compatible variants (providers.py:268-293) |
| Automatic parameter suggestions + unrestricted expert/backend-specific params | **No** | router passes only temperature (model_router.py:222-234); no suggestions; params arbitrary but dropped |
| Per-model and per-role profiles (context/reasoning/sampling/tool-calling/prompt templates, project bindings, switch preserving overrides) | **Partial** | role model/temperature in YAML; no persistent profiles or project bindings; router project_roles exists but is not wired anywhere |
| Capability states declared/detected/tested/unknown + optional benchmarks/profiling, warnings not rejection | **Partial** | measured/declared/unknown/unavailable store exists; no UI states; measured-only gating rejects unmeasured experimental use |
| Flexible routing local/external/embedding/multimodal with explanations/override/permission | **Partial** | router exists (unwired) with role/fallback/capability/permission/resource logic; no embedding or multimodal route, no live wiring/explanations/user override |
| Model Hub GUI/CLI/API provider+profile management, credential redaction, no hardcoded approved lists | **No** | read-only table/settings; no management commands; config edit only |
| Acceptance scenario (custom OpenAI-compatible + llama.cpp + LM Studio + Ollama namespace/fine-tune, profiles, warnings, routing explanations, permissions) | **No** | no such end-to-end scenario |

## 5. Dedupe mapping (directive sub-capability -> existing ID / new ID)

| Sub-capability | Existing coverage | New requirement | Decision |
|---|---|---|---|
| Multi-provider discovery/health/loaded/unload | NL-BP-008 (verified) | - | covered foundation, retained unchanged |
| Built-in presets with editable defaults | config/models.yaml (hand-edited YAML only) | NL-BP-224 | presets exist as raw YAML; first-class editable presets are new |
| Custom provider profiles (arbitrary URL/model/auth/headers/protocol, secret refs, import/export/reuse) | NL-BP-008/010 (fixed schema) | NL-BP-225 | new profile model/store |
| Auto discovery + always-available manual entry | NL-BP-008 (auto discovery only) | NL-BP-226 | manual entry/fallback is new |
| Extensible protocol adapters, no closed provider list | NL-BP-008 (closed kind branch) | NL-BP-227 | adapter registry is new |
| Automatic parameter suggestions + expert/backend-specific params | NL-BP-010 partial, NL-BP-068 planned | NL-BP-228 | new parameter profile/suggestion layer |
| Per-model/per-role profiles + project bindings/switch overrides | NL-BP-010/011 partial, NL-BP-068 planned | NL-BP-229 | profiles/bindings are new |
| Capability states declared/detected/tested/unknown + optional benchmarks/profiling, warnings not rejection | NL-BP-009 partial, NL-BP-069/183 planned | NL-BP-230 | new presentation/policy layer; competence lab remains separate |
| Flexible routing local/external/embedding/multimodal, explanations, override, permission/cloud-spend enforcement | NL-BP-010 partial; router module unwired; NL-BP-070 partial; NL-BP-168 partial | NL-BP-231 | new live routing surface; reuses permission/cloud gates |
| Model Hub GUI/CLI/API provider+profile management, credential redaction, no hardcoded approved lists | NL-BP-036 partial (read-only UI) | NL-BP-232 | new management surface |
| Model lifecycle load/unload/storage UI | NL-BP-036 partial | - | retained; 232 adds provider/profile management, no duplicate |
| Competence benchmarks/hardware profiling | NL-BP-069/183 planned | - | retained; 230 may consume, not duplicate |
| Permission/cloud-spending enforcement | NL-BP-168/072 partial | - | retained; 231 enforces existing policy |
| Acceptance scenario | - | NL-BP-233 | new end-to-end acceptance |

## 6. New requirements registered (status planned, program stage 9)

| ID | Priority | Area | Dependencies | Summary |
|---|---|---|---|---|
| NL-BP-224 | P0 | core | 008, 010, 036 | Built-in provider presets with editable defaults (Ollama, llama.cpp, LM Studio, OpenAI-compatible, extensible), presets as conveniences not restrictions |
| NL-BP-225 | P0 | core | 008, 224 | Custom provider profiles: arbitrary base URL/model id/auth/headers/protocol, secret references, editable/importable/exportable/reusable |
| NL-BP-226 | P0 | core | 008, 224, 225 | Automatic discovery where supported plus always-available manual entry (Ollama namespaces/tags, OpenAI-compatible /models, llama.cpp/LM Studio) |
| NL-BP-227 | P0 | core | 008, 225 | Extensible provider protocol adapters registered by capability; no closed provider list |
| NL-BP-228 | P0 | core | 010, 225, 068 | Automatic parameter suggestions plus unrestricted expert configuration incl. backend-specific extra parameters |
| NL-BP-229 | P0 | core | 010, 011, 068, 225 | Per-model and per-role profiles (context/reasoning/sampling/tool-calling/prompt templates, project bindings, switching preserves overrides) |
| NL-BP-230 | P0 | core | 009, 069, 183, 070 | Capability states declared/detected/tested/unknown + optional benchmarks/hardware profiling; warnings not arbitrary rejection; gating only where explicitly required |
| NL-BP-231 | P0 | core | 008, 009, 010, 070, 168, 225, 230 | Flexible routing local/external/embedding/multimodal with explanations, user override and existing permission/cloud-spending enforcement |
| NL-BP-232 | P0 | studio | 036, 224, 225, 229, 231 | Model Hub GUI/CLI/API provider+profile management (switch/edit/import/export/reuse, presets/custom, credential redaction, no hardcoded approved lists) |
| NL-BP-233 | P0 | release | 224, 225, 226, 227, 228, 229, 230, 231, 232 | Acceptance scenario: custom OpenAI-compatible + llama.cpp + LM Studio + Ollama community namespace/custom fine-tune; discovery+manual; profiles; unknown-capability warnings; routing explanations/overrides; unsupported-combination warnings without arbitrary rejection; permission/cloud-spending controls; import/export/reuse |

## 7. Blockers, risks and human/external decisions

- **Stage 9 is pending** and depends on stages 4 and 7; stage 7 is itself pending/partially implemented. No stage status was changed by this import.
- **Existing requirements NL-BP-008/009/010/036/068/069/183/208 stay unchanged.** In particular 008 remains the verified discovery core; the new requirements extend the product surface without rewriting acceptance.
- **Live wiring gap:** the `ModelRouter` is tested but not instantiated in product code; 231 requires real integration into missions/supervisor with explanations and user override, without weakening the existing permission/cloud gates (NL-BP-168/072).
- **Manual entry is the escape hatch** for providers without discovery APIs; it must be always available but never bypass permissions/cloud-spending policy.
- **Capability warnings vs gates:** ordinary experimental use must warn on unknown/declared capabilities, not reject; hard refusals remain only where a task explicitly requires a measured capability or a policy demands it.
- **No hardcoded approved model-family/architecture/quantization/provider lists** may be introduced by presets/adapters; presets are conveniences and must be editable/removable.
- **No model download** is part of this directive; HF acquisition (NL-BP-208) and competence benchmarks (NL-BP-069/183) remain separate planned requirements and are optional for 230/233.
- **No network/model run** was performed by this audit; live provider probing remains an explicit user action.

## 8. Verification commands used (read-only; no network/model/mission runs)

- `nl_coding_agent/models/providers.py:24-307`; `models/ollama_registry.py:12,45-120`; `models/model_router.py:48-301`; `models/capabilities.py:1-257`.
- `nl_coding_agent/gui/widgets/models_panel.py:37-288`; `gui/widgets/settings_panel.py:59-81,261-268`; `gui/main_window.py` model page wiring.
- `nl_coding_agent/app/services.py:197-236`; `nl_coding_agent/cli.py:749,770-772,785-787,805-807,816-818`.
- `config/models.yaml:1-43` (presets and roles, hand-edited YAML).
- `git grep "ModelRouter("` in product code: no live instantiation.
- `cmd /c findstr /s /i "preset|lm_studio|llama_cpp|provider_profile|custom provider" nl_coding_agent\*.py`: only the closed `kind` branch in providers.py:282; no preset/profile system.
- `cmd /c findstr /s /i "embedding|embed" nl_coding_agent\*.py`: CrewAI memory embedder policy (agents/crew_backend.py:198-250) and unrelated strings - no embedding route.
- Tests inspected: `tests/test_model_hub.py` (7), `tests/test_model_router.py` (1), `tests/test_model_capabilities.py` (1), `tests/test_crew_backend.py` (15).
- `docs/product-blueprint/INDEX.json` statuses: 008 verified; 009/010/036 partial; 068/069/183/208 planned.

## 9. Change record

New documentation file and the queue-only backlog update it justifies. The preserved addendum bundle under `docs/product-blueprint/addenda/` is unchanged. No application code, tests, configuration, models, missions or network state were changed, and no commit was created by this task.
