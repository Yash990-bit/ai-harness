# Architecture Baseline — Harness Kit

> Phase 1 discovery document. Everything below is traced from actual source
> inspection, not assumed from README text.

---

## Existing Architecture

### Component Map

| Component | Purpose | Key Files | Entry Point | Dependencies |
|---|---|---|---|---|
| **Odin CLI** | Multi-agent orchestration CLI | `odin/src/odin/cli.py` | `odin` (console_scripts via pyproject.toml) | fire, rich, pydantic, httpx, pyyaml, python-dotenv |
| **Orchestrator** | Core engine: planning, execution, spec management | `odin/src/odin/orchestrator.py` (6 k lines) | `Orchestrator` class, instantiated by CLI | harnesses, task manager, spec store, cost tracker |
| **Harness Registry** | Pluggable agent integrations (Claude, Codex, Gemini, GLM, MiniMax, AGY, Mock) | `odin/src/odin/harnesses/` | `@register_harness` decorator → `get_harness()` | `BaseHarness` ABC, `AgentConfig` model |
| **Config System** | YAML + env var config loading with layered precedence | `odin/src/odin/config.py` | `load_config()` | pyyaml, python-dotenv |
| **Task Manager** | Local JSON-file task store + optional TaskIt REST backend | `odin/src/odin/taskit/` | `TaskManager` class | local disk or TaskIt HTTP API |
| **DAG Engine** | Dependency graph algorithms (ready/waiting/blocked, cycle detection) | `odin/src/odin/dag.py` | Pure functions, no class | None (pure algorithm) |
| **Spec System** | Spec archives — decomposed work units with derived status | `odin/src/odin/specs.py` | `SpecStore`, `SpecArchive` | local disk |
| **Cost Tracking** | Per-task token/cost accounting | `odin/src/odin/cost_tracking/` | `CostTracker`, `CostStore` | local disk |
| **TaskIt Backend** | Django REST API — boards, tasks, users, execution, analytics | `taskit/taskit-backend/` | `manage.py` → Django | Django, DRF, Celery, SQLite |
| **TaskIt Frontend** | React/TypeScript dashboard — kanban, DAG view, timeline | `taskit/taskit-frontend/` | `npm run dev` (Vite) | React, TypeScript, Vite |
| **Celery Workers** | Background DAG executor, merge queue, reflection queue | `taskit/taskit-backend/tasks/execution/celery_dag.py` | Celery app (`config/celery.py`) | Celery, Django |
| **Provider Quota** | CLI to check AI provider usage quotas | `harness_usage_status/` | `harness-usage-status` CLI | httpx, pyyaml |
| **Forced Provider** | Override base provider via env var (`FORCED_BASE_PROVIDER`) | `odin/src/odin/forced_provider.py` | `resolve_forced_provider()` | shutil.which for CLI check |
| **Doctor** | Health-check: services, agent CLIs, sandbox, host | `odin/src/odin/doctor.py` | `odin doctor` CLI command | all agent CLIs, TaskIt, sandbox |

### How Components Communicate

```
User
  │
  ▼
odin CLI  ──(fire)──▶  OdinCLI class
  │                        │
  │  load_config()         ▼
  │  ◀── .odin/config.yaml + .env + env vars
  │
  ▼
Orchestrator
  │
  ├──▶ TaskManager (local JSON or TaskIt REST)
  │         └── TaskIt Backend (Django, SQLite, Celery)
  │
  ├──▶ Harness Registry
  │         └── get_harness(name, config) → BaseHarness subclass
  │              ├── ClaudeHarness   (CLI subprocess: `claude -p`)
  │              ├── CodexHarness    (CLI subprocess: `codex`)
  │              ├── GeminiHarness   (CLI subprocess: `gemini`)
  │              ├── GLMHarness      (API: httpx, uses ZAI_API_KEY)
  │              ├── MinimaxHarness  (API: httpx, uses MINIMAX_API_KEY)
  │              ├── AgyHarness      (CLI subprocess: `agy`)
  │              └── MockHarness     (in-memory, no external call)
  │
  ├──▶ SpecStore (local .odin/specs/)
  │
  └──▶ CostTracker (local .odin/costs/)
```

### Startup Flow (Current)

```
./dev.sh
  │
  ├── source scripts/lib/provision.sh → provision_environment()
  │     ├── python3 -m venv .venv
  │     ├── pip install -r taskit-backend/requirements.txt
  │     ├── pip install -e odin/
  │     ├── npm install (frontend)
  │     ├── python manage.py migrate
  │     └── python manage.py seedmodels
  │
  ├── Start Django backend (:9100)
  ├── Start Vite frontend (:9200)
  ├── Start Celery worker (prefork, concurrency=3)
  ├── Start Celery merge worker (threads)
  └── Start Celery reflection worker (threads)
```

### Credential Flow (Current)

| Credential | Env Var | Used By | Mechanism |
|---|---|---|---|
| MiniMax API key | `MINIMAX_API_KEY` | GLM harness, config.py `ENV_VAR_MAP` | `os.environ.get()` in config loader |
| GLM/Zhipu API key | `ZAI_API_KEY` | MinMax harness, config.py `ENV_VAR_MAP` | `os.environ.get()` in config loader |
| TaskIt admin user | `ODIN_ADMIN_USER` | TaskIt auth | `_apply_taskit_auth_env()` in config.py |
| TaskIt admin password | `ODIN_ADMIN_PASSWORD` | TaskIt auth | `_apply_taskit_auth_env()` in config.py |
| Firebase API key | `ODIN_FIREBASE_API_KEY` | TaskIt Firebase auth | Backend settings.py |
| Forced provider | `FORCED_BASE_PROVIDER` | Provider override | `forced_provider.py` |
| Forced model | `FORCED_BASE_MODEL` | Model override | `forced_provider.py` |
| Claude OAuth | `CLAUDE_CODE_OAUTH_TOKEN` | Claude CLI | External CLI reads it directly |
| AGY secret | `AGY_SECRET` | AGY CLI | External CLI reads it directly |

**Key observation:** CLI-based harnesses (Claude, Codex, Gemini, AGY) authenticate
through their own CLI toolchain, not through Odin's config. API-based harnesses
(GLM, MiniMax) read keys from env vars via `config.py`'s `ENV_VAR_MAP`.

There is **no** existing `AI_API_KEY` env var. The hackathon's standardized
`AI_API_KEY` will need a thin mapping layer.

---

## Components We Will Reuse

| Component | Status | Reason |
|---|---|---|
| **Odin CLI** (`odin/src/odin/cli.py`) | REUSE | Well-structured Fire-based CLI with all needed commands. The `odin plan`, `odin exec`, `odin status` commands form the core hackathon workflow. |
| **Orchestrator** (`odin/src/odin/orchestrator.py`) | REUSE | 6 k-line engine handles planning, execution, spec management, worktree isolation. This IS the harness. |
| **Harness Registry** (`odin/src/odin/harnesses/`) | REUSE | Clean `@register_harness` decorator pattern. New providers plug in with zero changes to existing code. |
| **BaseHarness** (`odin/src/odin/harnesses/base.py`) | REUSE | Well-defined abstract interface with `execute()`, `is_available()`, evidence ladder, status validation. |
| **Config System** (`odin/src/odin/config.py`) | MODIFY | Needs a small adapter to map `AI_API_KEY` into the existing `ENV_VAR_MAP` mechanism. The layered config (env → yaml → defaults) is exactly what we need. |
| **DAG Engine** (`odin/src/odin/dag.py`) | REUSE AS-IS | Pure-algorithm module with no coupling. Handles dependency ordering for task decomposition. |
| **Task Manager** (`odin/src/odin/taskit/`) | REUSE | Local JSON backend works without TaskIt server. Pluggable backend design (`local` vs `taskit`) means hackathon can run standalone. |
| **Spec System** (`odin/src/odin/specs.py`) | REUSE AS-IS | Manages spec archives and derives status from tasks. No changes needed. |
| **Cost Tracking** (`odin/src/odin/cost_tracking/`) | REUSE AS-IS | Per-task cost accounting. Useful for hackathon analytics. |
| **MockHarness** (`odin/src/odin/harnesses/mock.py`) | REUSE | Critical for testing: `odin exec <task_id> --mock` skips backend writes. |
| **Doctor** (`odin/src/odin/doctor.py`) | REUSE | `odin doctor` validates the environment — exactly what evaluators need after `make setup`. |
| **Forced Provider** (`odin/src/odin/forced_provider.py`) | MODIFY | Currently only allows `gemini`. Will need expansion or the `AI_API_KEY` adapter. |
| **provision.sh** (`scripts/lib/provision.sh`) | WRAP | The shared provisioning script handles venv, deps, migrations, seeds. `make setup` wraps this. |
| **verify.sh** (`scripts/verify.sh`) | WRAP | Runs all 4 test suites with a summary table. `make test` wraps this. |
| **TaskIt Backend** | NOT NEEDED (Phase 1) | Full Django+Celery stack is overkill for hackathon evaluation. Odin works with `board_backend: local` (local JSON files). |
| **TaskIt Frontend** | NOT NEEDED (Phase 1) | React dashboard adds complexity. Evaluators need CLI, not UI. |
| **Celery Workers** | NOT NEEDED (Phase 1) | Background execution via Celery requires the full TaskIt stack. Odin CLI's foreground `exec` is sufficient. |

---

## Hackathon Compatibility Gaps

| Requirement | Current State | Gap | Required Change |
|---|---|---|---|
| **Root Makefile** | Does not exist | No `Makefile` at repo root | Create `Makefile` wrapping existing scripts |
| **`make setup`** | `./dev.sh` + `install.sh` + `scripts/lib/provision.sh` | No single `make setup` target | Create target that calls provision logic |
| **`make run`** | `./dev.sh` (starts 5 services) or `odin plan/exec` | Too complex for evaluator; starts full stack | Create target that starts odin CLI in hackathon mode |
| **`make test`** | `scripts/verify.sh` runs 4 suites | No `make test` target | Create target wrapping verify.sh |
| **`make clean`** | No clean target | No cleanup mechanism | Create target to remove `.odin/`, `.venv/`, caches |
| **`AI_API_KEY`** | Not recognized; uses `MINIMAX_API_KEY`, `ZAI_API_KEY`, per-CLI auth | Evaluator's `AI_API_KEY` is not read | Add env var mapping in config.py |
| **Model configuration** | `FORCED_BASE_PROVIDER` + `FORCED_BASE_MODEL` env vars | Only allows `gemini`; no `AI_API_KEY` | Add `AI_MODEL`, `AI_PROVIDER` env vars |
| **Text-only input** | All harnesses are text-only CLI/API | ✅ No gap | None |
| **No hardcoded secrets** | No secrets found in committed code | ✅ No gap | None (confirmed via grep audit) |
| **`.env` protected** | `.env` in `.gitignore` (line 145) | ✅ No gap | None |
| **Clean startup** | `provision_environment()` is idempotent | ✅ No gap | Wrap in Makefile |
| **Reproducible** | `install.sh` handles fresh machines | ✅ Works on macOS/Linux | Wrap in Makefile |

---

## Text-Only Confirmation

All existing harnesses operate in text-only mode:
- CLI harnesses (`claude -p`, `codex`, `gemini`) send text prompts via subprocess
- API harnesses (GLM, MiniMax) use text-only HTTP endpoints
- No image/audio/video input is present anywhere in the codebase

This satisfies the hackathon's text-only requirement without modification.
