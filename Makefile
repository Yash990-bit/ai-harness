# Makefile — AI Harness Hackathon 2026
#
# Standardized evaluation interface. The evaluator runs:
#   export AI_API_KEY="PROVIDED_KEY"
#   make setup
#   make run
#
# No credentials are stored in this file.

.PHONY: setup run test clean doctor solve

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
	@if [ -n "$(TASK)" ]; then \
		echo "══════════════════════════════════════" ; \
		echo "  Executing Autonomous Task: $(TASK)" ; \
		echo "══════════════════════════════════════" ; \
		$(PY) -m odin.cli solve --prompt "$(TASK)" $(if $(VERIFY),--verify-cmd "$(VERIFY)",) $(if $(MOCK),--mock,) ; \
	elif [ -n "$${TASK:-}" ]; then \
		echo "══════════════════════════════════════" ; \
		echo "  Executing Autonomous Task: $${TASK}" ; \
		echo "══════════════════════════════════════" ; \
		$(PY) -m odin.cli solve --prompt "$${TASK}" $${VERIFY:+--verify-cmd "$$VERIFY"} $${MOCK:+--mock} ; \
	elif [ -n "$(SPEC)" ]; then \
		echo "══════════════════════════════════════" ; \
		echo "  Executing Autonomous Spec: $(SPEC)" ; \
		echo "══════════════════════════════════════" ; \
		$(PY) -m odin.cli solve "$(SPEC)" $(if $(VERIFY),--verify-cmd "$(VERIFY)",) $(if $(MOCK),--mock,) ; \
	elif [ -n "$${SPEC:-}" ]; then \
		echo "══════════════════════════════════════" ; \
		echo "  Executing Autonomous Spec: $${SPEC}" ; \
		echo "══════════════════════════════════════" ; \
		$(PY) -m odin.cli solve "$${SPEC}" $${VERIFY:+--verify-cmd "$$VERIFY"} $${MOCK:+--mock} ; \
	else \
		echo "[run] Checking harness health & provider configuration..." ; \
		echo "" ; \
		$(PY) -m odin.cli doctor --fast 2>/dev/null || \
			echo "[run] odin doctor completed." ; \
		echo "" ; \
		echo "══════════════════════════════════════" ; \
		echo "  Harness is ready for autonomous execution." ; \
		echo "══════════════════════════════════════" ; \
		echo "" ; \
		echo "  Usage examples:" ; \
		echo "    make run TASK=\"Fix IndexError in sequence parser\"" ; \
		echo "    make run SPEC=\"path/to/spec.md\"" ; \
		echo "    make solve TASK=\"Fix bug\" VERIFY=\"pytest tests/test_bug.py\"" ; \
		echo "" ; \
	fi

# ──────────────────────────────────────────────
# solve: autonomous issue resolution & patch creation
# ──────────────────────────────────────────────
solve:
	@if [ -n "$(TASK)" ]; then \
		$(PY) -m odin.cli solve --prompt "$(TASK)" $(if $(VERIFY),--verify-cmd "$(VERIFY)",) $(if $(MOCK),--mock,) ; \
	elif [ -n "$${TASK:-}" ]; then \
		$(PY) -m odin.cli solve --prompt "$${TASK}" $${VERIFY:+--verify-cmd "$$VERIFY"} $${MOCK:+--mock} ; \
	elif [ -n "$(SPEC)" ]; then \
		$(PY) -m odin.cli solve "$(SPEC)" $(if $(VERIFY),--verify-cmd "$(VERIFY)",) $(if $(MOCK),--mock,) ; \
	elif [ -n "$${SPEC:-}" ]; then \
		$(PY) -m odin.cli solve "$${SPEC}" $${VERIFY:+--verify-cmd "$$VERIFY"} $${MOCK:+--mock} ; \
	else \
		echo "Usage: make solve TASK=\"Issue prompt\" [VERIFY=\"pytest ...\"] [MOCK=1]" ; \
		echo "       make solve SPEC=\"spec.md\" [VERIFY=\"pytest ...\"] [MOCK=1]" ; \
	fi

# ──────────────────────────────────────────────
# test: run the test suites
# ──────────────────────────────────────────────
test:
	@echo "══════════════════════════════════════"
	@echo "  AI Harness — Test"
	@echo "══════════════════════════════════════"
	@echo ""
	@echo "[test] Running hackathon baseline & integration test suites..."
	@$(PY) -m pytest tests/test_hackathon_baseline.py tests/test_phase2_integration.py tests/test_phase3_solver.py tests/test_phase4_error_ledger.py -v 2>&1
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
