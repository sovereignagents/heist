# Makefile — heist
# Requires: uv, python 3.11

.DEFAULT_GOAL := help
.PHONY: help install install-dev verify lint format typecheck \
        generate-audio demo-heist test test-unit test-integration \
        clean clean-logs clean-all

# ---------------------------------------------------------------------------
# Paths & settings
# ---------------------------------------------------------------------------

UV      := uv
SRC     := src/heist
TESTS   := tests
LOG_DIR := .logs

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help:
	@echo ""
	@echo "  heist — LangGraph voice security demo"
	@echo ""
	@echo "  Setup"
	@echo "    make install          Install all dependencies (editable, prod)"
	@echo "    make install-dev      Install prod + dev + test deps"
	@echo "    make verify           Pre-flight checks (API keys, services)"
	@echo ""
	@echo "  Code quality"
	@echo "    make lint             Run ruff linter"
	@echo "    make format           Auto-format with ruff"
	@echo "    make typecheck        Run mypy"
	@echo ""
	@echo "  Demo"
	@echo "    make generate-audio   Pre-generate user voice audio files"
	@echo "    make demo-heist       Run the full heist security demo"
	@echo ""
	@echo "  Tests"
	@echo "    make test             Run all tests"
	@echo "    make test-unit        Run unit tests only (no live services)"
	@echo "    make test-integration Run integration tests (requires API keys)"
	@echo ""
	@echo "  Housekeeping"
	@echo "    make clean            Remove __pycache__, .pyc, build artefacts"
	@echo "    make clean-logs       Remove session log files"
	@echo "    make clean-all        clean + clean-logs + remove .venv"
	@echo ""

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

install:
	$(UV) sync

install-dev:
	$(UV) sync --all-extras

verify:
	$(UV) run heist-verify

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------

lint:
	$(UV) run ruff check $(SRC) $(TESTS)

format:
	$(UV) run ruff format $(SRC) $(TESTS)
	$(UV) run ruff check --fix $(SRC) $(TESTS)

typecheck:
	$(UV) run mypy $(SRC)

# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

generate-audio:
	$(UV) run heist-audio

demo-heist:
	$(UV) run heist-demo

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

test:
	$(UV) run pytest $(TESTS) -v

test-unit:
	$(UV) run pytest $(TESTS) -v -m "not integration"

test-integration:
	$(UV) run pytest $(TESTS) -v -m integration

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Clean."

clean-logs:
	find $(LOG_DIR) -name "*.jsonl" -delete
	find $(LOG_DIR) -name "*.txt" -delete
	@echo "✓ Logs cleared."

clean-all: clean clean-logs
	rm -rf .venv
	@echo "✓ Full clean done. Run 'make install' to start fresh."

# ==============================================================================
# 🔧 Tooling (annotate + flatten)
# ==============================================================================
ANNOTATE_SCOPE         ?= .
ANNOTATE_EXT           ?= .py,.yaml,.yml,.toml,.env
ANNOTATE_MAX_NEIGHBORS ?= 6

.PHONY: annotate
annotate: ## Add/update QV-LLM header blocks across repo files
	$(PYTHON) scripts/annotate_headers.py \
		--scope "$(ANNOTATE_SCOPE)" \
		--extensions "$(ANNOTATE_EXT)" \
		--max-neighbors "$(ANNOTATE_MAX_NEIGHBORS)" \
		--remove-legacy-path-line

FLATTEN_OUT   ?= _transient-files/flatten
FLATTEN_EXT   ?= .py,.yaml,.yml,.toml,.env,.example,.md
FLATTEN_SKIP  ?= .git,.venv,__pycache__,.mypy_cache,.pytest_cache,.ruff_cache,build,dist,.egg-info,node_modules
FLATTEN_SCOPE ?= .
MAX_BYTES     ?= 4000000

.PHONY: flatten
flatten: ## Flatten repo into a single shareable text bundle
	@echo "$(BLUE)Flattening '$(FLATTEN_SCOPE)' → $(FLATTEN_OUT)...$(RESET)"
	@mkdir -p "$(FLATTEN_OUT)"
	$(PYTHON) scripts/flatten.py \
		--mode scope \
		--scope "$(FLATTEN_SCOPE)" \
		--out-dir "$(FLATTEN_OUT)" \
		--extensions "$(FLATTEN_EXT)" \
		--skip-dirs "$(FLATTEN_SKIP)" \
		--exclude "flat.txt" \
		--exclude "_transient-files/**" \
		$(if $(MAX_BYTES),--max-bytes $(MAX_BYTES),)
	@echo "$(GREEN)✓ Done. See: $(FLATTEN_OUT)/manifest.md$(RESET)"

.PHONY: flatten-scope
flatten-scope: ## Flatten a specific directory: make flatten-scope SCOPE=path/to/dir
	@test -n "$(SCOPE)" || (echo "Usage: make flatten-scope SCOPE=path/to/dir" && exit 1)
	$(PYTHON) scripts/flatten.py \
		--mode scope \
		--scope "$(SCOPE)" \
		--out-dir "$(FLATTEN_OUT)" \
		--extensions "$(FLATTEN_EXT)" \
		--skip-dirs "$(FLATTEN_SKIP)" \
		--exclude "flat.txt" \
		--exclude "_transient-files/**" \
		--max-bytes 4000000

.PHONY: flatten-clean
flatten-clean: ## Remove transient flatten outputs
	rm -rf "$(FLATTEN_OUT)"