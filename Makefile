# Makefile — AI Harness Hackathon 2026
#
# Standardized evaluation interface. The evaluator runs:
#   export AI_API_KEY="PROVIDED_KEY"
#   make setup
#   make run
#
# No credentials are stored in this file.

.PHONY: setup run test clean doctor solve tui

SHELL := /bin/bash
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# ──────────────────────────────────────────────
# setup: install the harness from scratch
# ──────────────────────────────────────────────
# Installs odin (the orchestration CLI) which is the core harness.
# The full TaskIt stack (Django, Celery, frontend) is optional and
# only needed for the board UI — not for hackathon evaluation.
setup:
	@echo "══════════════════════════════════════"
	@echo "  AI Harness — Setup"
	@echo "══════════════════════════════════════"
	@echo ""
	@# Step 1: Create virtualenv if needed
	@if [ ! -f "$(VENV)/bin/activate" ]; then \
		echo "[setup] Creating virtual environment..." ; \
		python3 -m venv $(VENV) ; \
	else \
		echo "[setup] Virtual environment exists." ; \
	fi
	@# Step 2: Install odin (the harness CLI) — this is the critical path
	@echo "[setup] Installing odin (orchestration CLI)..."
	@$(PIP) install -e odin/ --quiet 2>&1 | tail -5
	@# Verify odin installed correctly
	@$(PY) -c "from odin.config import load_config; print('[setup] odin package: OK')"
	@# Step 3: Attempt backend deps (best-effort — psycopg2 needs pg_config)
	@echo "[setup] Installing backend deps (best-effort)..."
	@$(PIP) install -r taskit/taskit-backend/requirements.txt --quiet 2>&1 | tail -3 || \
		echo "[setup] WARNING: Some backend deps failed (likely psycopg2 — needs PostgreSQL headers)." && \
		echo "[setup]          This is OK for hackathon evaluation. Odin works standalone."
	@# Step 4: Run migrations if Django is available
	@$(PY) -c "import django" 2>/dev/null && \
		( echo "[setup] Running migrations..." && \
		  $(PY) taskit/taskit-backend/manage.py migrate --run-syncdb --verbosity 0 2>/dev/null && \
		  $(PY) taskit/taskit-backend/manage.py seedmodels --verbosity 0 2>/dev/null || true \
		) || echo "[setup] Skipping migrations (Django not installed — OK for standalone mode)."
	@echo ""
	@echo "══════════════════════════════════════"
	@echo "  Setup complete."
	@echo "══════════════════════════════════════"
	@echo ""
	@echo "  Activate:  source $(VENV)/bin/activate"
	@echo "  Next:      make run"
	@echo ""

# Parameters (can be passed via `make TASK="..."` or environment `export TASK="..."`)
TASK ?=
SPEC ?=
VERIFY ?=
MOCK ?=

# ──────────────────────────────────────────────
# run: start the harness
# ──────────────────────────────────────────────
# Standard evaluation entry point.
# If TASK or SPEC is provided, runs autonomous solver to produce a solution patch.
# Otherwise, validates environment, runs doctor, and displays usage.
run:
	@echo "══════════════════════════════════════"
	@echo "  AI Harness — Run"
	@echo "══════════════════════════════════════"
	@if [ -z "$${AI_API_KEY:-}" ]; then \
		echo "" ; \
		echo "[run] WARNING: AI_API_KEY is not set." ; \
		echo "[run] The evaluator should run: export AI_API_KEY=\"PROVIDED_KEY\"" ; \
		echo "" ; \
	fi
	@echo "[run] Environment:"
	@echo "  AI_API_KEY:  $${AI_API_KEY:+set (hidden)}"
	@echo "  AI_PROVIDER: $${AI_PROVIDER:-auto (defaults to gemini)}"
	@echo "  AI_MODEL:    $${AI_MODEL:-default}"
	@echo ""
	@export SOLVER_TASK="$${TASK:-$(TASK)}" ; \
	export SOLVER_SPEC="$${SPEC:-$(SPEC)}" ; \
	export SOLVER_VERIFY="$${VERIFY:-$(VERIFY)}" ; \
	export SOLVER_MOCK="$${MOCK:-$(MOCK)}" ; \
	if [ -n "$$SOLVER_TASK" ]; then \
		echo "══════════════════════════════════════" ; \
		echo "  Executing Autonomous Task: $$SOLVER_TASK" ; \
		echo "══════════════════════════════════════" ; \
		$(PY) -c 'import os, subprocess, sys; cmd=[sys.argv[1], "-m", "odin.cli", "solve", "--prompt", os.environ["SOLVER_TASK"]]; (cmd.extend(["--verify-cmd", os.environ["SOLVER_VERIFY"]]) if os.environ.get("SOLVER_VERIFY") else None); (cmd.append("--mock") if os.environ.get("SOLVER_MOCK") else None); sys.exit(subprocess.run(cmd).returncode)' $(PY) ; \
	elif [ -n "$$SOLVER_SPEC" ]; then \
		echo "══════════════════════════════════════" ; \
		echo "  Executing Autonomous Spec: $$SOLVER_SPEC" ; \
		echo "══════════════════════════════════════" ; \
		$(PY) -c 'import os, subprocess, sys; cmd=[sys.argv[1], "-m", "odin.cli", "solve", os.environ["SOLVER_SPEC"]]; (cmd.extend(["--verify-cmd", os.environ["SOLVER_VERIFY"]]) if os.environ.get("SOLVER_VERIFY") else None); (cmd.append("--mock") if os.environ.get("SOLVER_MOCK") else None); sys.exit(subprocess.run(cmd).returncode)' $(PY) ; \
	else \
		$(PY) -m odin.tui ; \
	fi

# ──────────────────────────────────────────────
# solve: autonomous issue resolution & patch creation
# ──────────────────────────────────────────────
solve:
	@export SOLVER_TASK="$${TASK:-$(TASK)}" ; \
	export SOLVER_SPEC="$${SPEC:-$(SPEC)}" ; \
	export SOLVER_VERIFY="$${VERIFY:-$(VERIFY)}" ; \
	export SOLVER_MOCK="$${MOCK:-$(MOCK)}" ; \
	if [ -n "$$SOLVER_TASK" ]; then \
		$(PY) -c 'import os, subprocess, sys; cmd=[sys.argv[1], "-m", "odin.cli", "solve", "--prompt", os.environ["SOLVER_TASK"]]; (cmd.extend(["--verify-cmd", os.environ["SOLVER_VERIFY"]]) if os.environ.get("SOLVER_VERIFY") else None); (cmd.append("--mock") if os.environ.get("SOLVER_MOCK") else None); sys.exit(subprocess.run(cmd).returncode)' $(PY) ; \
	elif [ -n "$$SOLVER_SPEC" ]; then \
		$(PY) -c 'import os, subprocess, sys; cmd=[sys.argv[1], "-m", "odin.cli", "solve", os.environ["SOLVER_SPEC"]]; (cmd.extend(["--verify-cmd", os.environ["SOLVER_VERIFY"]]) if os.environ.get("SOLVER_VERIFY") else None); (cmd.append("--mock") if os.environ.get("SOLVER_MOCK") else None); sys.exit(subprocess.run(cmd).returncode)' $(PY) ; \
	else \
		echo "Usage: make solve TASK=\"Issue prompt\" [VERIFY=\"pytest ...\"] [MOCK=1]" ; \
		echo "       make solve SPEC=\"spec.md\" [VERIFY=\"pytest ...\"] [MOCK=1]" ; \
	fi

# ──────────────────────────────────────────────
# textual / gui: full-screen Textual desktop-like dashboard
# ──────────────────────────────────────────────
textual:
	@$(PY) -m odin.textual_app

gui: textual

# ──────────────────────────────────────────────
# test: run the test suites
# ──────────────────────────────────────────────
test:
	@echo "══════════════════════════════════════"
	@echo "  AI Harness — Test"
	@echo "══════════════════════════════════════"
	@echo ""
	@echo "[test] Running hackathon baseline & integration test suites..."
	@$(PY) -m pytest tests/test_hackathon_baseline.py tests/test_phase2_integration.py tests/test_phase3_solver.py tests/test_phase4_error_ledger.py tests/test_e2e_swe_benchmark.py tests/test_tui.py tests/test_deepseek_support.py tests/test_textual_app.py -v 2>&1
	@echo ""
	@echo "[test] Running odin unit tests..."
	@cd odin && ../$(PY) -m pytest tests/unit/ -q --tb=short 2>&1

# ──────────────────────────────────────────────
# clean: remove generated artifacts
# ──────────────────────────────────────────────
# Safe cleanup: removes caches, generated state, and databases.
# Does NOT remove: source code, .venv (use clean-all), node_modules,
# config templates, or user repositories.
clean:
	@echo "══════════════════════════════════════"
	@echo "  AI Harness — Clean"
	@echo "══════════════════════════════════════"
	@echo "[clean] Removing .odin/ (local task state)..."
	@rm -rf .odin/
	@echo "[clean] Removing Python caches..."
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "[clean] Removing dev logs..."
	@rm -rf .dev-logs/ .verify-logs/
	@echo "[clean] Removing Celery artifacts..."
	@rm -rf taskit/taskit-backend/.celery/
	@rm -f celerybeat-schedule celerybeat-schedule.db celery.pidbox.exchange
	@echo "[clean] Removing SQLite databases..."
	@rm -f taskit/taskit-backend/db.sqlite3
	@rm -f taskit/taskit-backend/db.sqlite3-journal
	@echo "[clean] Done."

# ──────────────────────────────────────────────
# clean-all: full cleanup including venv
# ──────────────────────────────────────────────
.PHONY: clean-all
clean-all: clean
	@echo "[clean-all] Removing virtual environment..."
	@rm -rf $(VENV)
	@echo "[clean-all] Done."

# ──────────────────────────────────────────────
# doctor: quick environment health check
# ──────────────────────────────────────────────
doctor:
	@source $(VENV)/bin/activate 2>/dev/null; $(PY) -m odin.cli doctor

# ──────────────────────────────────────────────
# tui: interactive terminal user interface
# ──────────────────────────────────────────────
tui:
	@$(PY) -m odin.tui

