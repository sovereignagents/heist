# Makefile — heist
# Requires: uv, python 3.11

.DEFAULT_GOAL := help
.PHONY: help install install-dev verify lint format typecheck \
        generate-audio demo-heist test test-unit test-integration \
        clean clean-logs clean-all \
        annotate flatten flatten-scope flatten-clean

# ==============================================================================
# 🎨 Terminal colours
# ==============================================================================

GREEN   := $(shell tput -Txterm setaf 2)
YELLOW  := $(shell tput -Txterm setaf 3)
BLUE    := $(shell tput -Txterm setaf 4)
MAGENTA := $(shell tput -Txterm setaf 5)
RED     := $(shell tput -Txterm setaf 1)
RESET   := $(shell tput -Txterm sgr0)

# ==============================================================================
# 🛠️  Paths & settings
# ==============================================================================

UV      := uv
SRC     := src/heist
TESTS   := tests
LOG_DIR := .logs

ifneq (,$(wildcard .env))
    include .env
    export
endif

# ==============================================================================
# 📖 Help
# ==============================================================================

help: ## Show this help message
	@echo ''
	@echo '$(MAGENTA)🏦  The Heist — LangGraph Voice Security Demo$(RESET)'
	@echo ''
	@echo '$(YELLOW)First-time setup:$(RESET)'
	@echo '  $(GREEN)make install$(RESET)          Install all dependencies (editable, prod)'
	@echo '  $(GREEN)make install-dev$(RESET)      Install prod + dev + test deps'
	@echo '  $(GREEN)make generate-audio$(RESET)   Pre-generate user voice audio files'
	@echo ''
	@echo '$(YELLOW)Diagnostics:$(RESET)'
	@echo '  $(GREEN)make verify$(RESET)           Pre-flight checks (API keys, connectivity)'
	@echo ''
	@echo '$(YELLOW)Run the demo:$(RESET)'
	@echo '  $(GREEN)make demo-heist$(RESET)       🎭  Run The Heist at First National Bank'
	@echo ''
	@echo '$(YELLOW)Code quality:$(RESET)'
	@echo '  $(GREEN)make lint$(RESET)             Run ruff linter'
	@echo '  $(GREEN)make format$(RESET)           Auto-format with ruff'
	@echo '  $(GREEN)make typecheck$(RESET)        Run mypy'
	@echo ''
	@echo '$(YELLOW)Tests:$(RESET)'
	@echo '  $(GREEN)make test$(RESET)             Run all tests'
	@echo '  $(GREEN)make test-unit$(RESET)        Unit tests only  (no live services)'
	@echo '  $(GREEN)make test-integration$(RESET) Integration tests (requires API keys)'
	@echo ''
	@echo '$(YELLOW)Housekeeping:$(RESET)'
	@echo '  $(GREEN)make clean$(RESET)            Remove __pycache__, .pyc, build artefacts'
	@echo '  $(GREEN)make clean-logs$(RESET)       Remove session log files from .logs/'
	@echo '  $(GREEN)make clean-all$(RESET)        clean + clean-logs + remove .venv'
	@echo ''
	@echo '$(YELLOW)Tooling:$(RESET)'
	@echo '  $(GREEN)make annotate$(RESET)         Add/update QV-LLM header blocks'
	@echo '  $(GREEN)make flatten$(RESET)          Flatten repo into a shareable text bundle'
	@echo ''

# ==============================================================================
# 🚀 Setup
# ==============================================================================

install: ## Install all dependencies (editable, prod)
	@echo "$(BLUE)Installing dependencies...$(RESET)"
	$(UV) sync
	@echo "$(GREEN)✓ Setup complete.$(RESET)"

install-dev: ## Install prod + dev + test deps
	@echo "$(BLUE)Installing all extras...$(RESET)"
	$(UV) sync --all-extras
	@echo "$(GREEN)✓ Dev setup complete.$(RESET)"

verify: ## Pre-flight checks (API keys, connectivity)
	@echo "$(BLUE)Running pre-flight diagnostics...$(RESET)"
	$(UV) run python scripts/verify_setup.py

# ==============================================================================
# 🔍 Code quality
# ==============================================================================

lint: ## Run ruff linter
	@echo "$(BLUE)Linting $(SRC) and $(TESTS)...$(RESET)"
	$(UV) run ruff check $(SRC) $(TESTS)

format: ## Auto-format with ruff
	@echo "$(BLUE)Formatting...$(RESET)"
	$(UV) run ruff format $(SRC) $(TESTS)
	$(UV) run ruff check --fix $(SRC) $(TESTS)
	@echo "$(GREEN)✓ Format complete.$(RESET)"

typecheck: ## Run mypy
	@echo "$(BLUE)Type-checking $(SRC)...$(RESET)"
	$(UV) run mypy $(SRC)

# ==============================================================================
# 🎭 Demo
# ==============================================================================

generate-audio: ## Pre-generate user voice audio files via Speechmatics TTS
	@echo "$(BLUE)Generating audio files...$(RESET)"
	$(UV) run python scripts/generate_audio.py

demo-heist: ## Run The Heist at First National Bank security demo
	@echo "$(MAGENTA)Starting The Heist...$(RESET)"
	$(UV) run heist-demo

# ==============================================================================
# 🧪 Tests
# ==============================================================================

test: ## Run all tests
	@echo "$(BLUE)Running all tests...$(RESET)"
	$(UV) run pytest $(TESTS) -v

test-unit: ## Unit tests only (no live services)
	@echo "$(BLUE)Running unit tests...$(RESET)"
	$(UV) run pytest $(TESTS) -v -m "not integration"

test-integration: ## Integration tests (requires API keys)
	@echo "$(BLUE)Running integration tests...$(RESET)"
	$(UV) run pytest $(TESTS) -v -m integration

# ==============================================================================
# 🧹 Housekeeping
# ==============================================================================

clean: ## Remove __pycache__, .pyc, build artefacts
	@echo "$(YELLOW)Cleaning build artefacts...$(RESET)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)✓ Clean.$(RESET)"

clean-logs: ## Remove session log files from .logs/
	@echo "$(YELLOW)Clearing session logs...$(RESET)"
	find $(LOG_DIR) -name "*.jsonl" -delete
	find $(LOG_DIR) -name "*.txt" -delete
	@echo "$(GREEN)✓ Logs cleared.$(RESET)"

clean-all: clean clean-logs ## clean + clean-logs + remove .venv
	rm -rf .venv
	@echo "$(GREEN)✓ Full clean done. Run 'make install' to start fresh.$(RESET)"

# ==============================================================================
# 🔧 Tooling (annotate + flatten)
# ==============================================================================

ANNOTATE_SCOPE         ?= .
ANNOTATE_EXT           ?= .py,.yaml,.yml,.toml,.env
ANNOTATE_MAX_NEIGHBORS ?= 6

FLATTEN_OUT   ?= _transient-files/flatten
FLATTEN_EXT   ?= .py,.yaml,.yml,.toml,.env,.example,.md
FLATTEN_SKIP  ?= .git,.venv,__pycache__,.mypy_cache,.pytest_cache,.ruff_cache,build,dist,.egg-info,node_modules
FLATTEN_SCOPE ?= .
MAX_BYTES     ?= 4000000

annotate: ## Add/update QV-LLM header blocks across repo files
	@echo "$(BLUE)Annotating headers...$(RESET)"
	$(UV) run python scripts/annotate_headers.py \
		--scope "$(ANNOTATE_SCOPE)" \
		--extensions "$(ANNOTATE_EXT)" \
		--max-neighbors "$(ANNOTATE_MAX_NEIGHBORS)" \
		--remove-legacy-path-line
	@echo "$(GREEN)✓ Annotation complete.$(RESET)"

flatten: ## Flatten repo into a single shareable text bundle
	@echo "$(BLUE)Flattening '$(FLATTEN_SCOPE)' → $(FLATTEN_OUT)...$(RESET)"
	@mkdir -p "$(FLATTEN_OUT)"
	$(UV) run python scripts/flatten.py \
		--mode scope \
		--scope "$(FLATTEN_SCOPE)" \
		--out-dir "$(FLATTEN_OUT)" \
		--extensions "$(FLATTEN_EXT)" \
		--skip-dirs "$(FLATTEN_SKIP)" \
		--exclude "flat.txt" \
		--exclude "_transient-files/**" \
		$(if $(MAX_BYTES),--max-bytes $(MAX_BYTES),)
	@echo "$(GREEN)✓ Done. See: $(FLATTEN_OUT)/manifest.md$(RESET)"

flatten-scope: ## Flatten a specific directory: make flatten-scope SCOPE=path/to/dir
	@test -n "$(SCOPE)" || (echo "$(RED)Usage: make flatten-scope SCOPE=path/to/dir$(RESET)" && exit 1)
	$(UV) run python scripts/flatten.py \
		--mode scope \
		--scope "$(SCOPE)" \
		--out-dir "$(FLATTEN_OUT)" \
		--extensions "$(FLATTEN_EXT)" \
		--skip-dirs "$(FLATTEN_SKIP)" \
		--exclude "flat.txt" \
		--exclude "_transient-files/**" \
		--max-bytes $(MAX_BYTES)

flatten-clean: ## Remove transient flatten outputs
	@echo "$(YELLOW)Removing flatten outputs...$(RESET)"
	rm -rf "$(FLATTEN_OUT)"
	@echo "$(GREEN)✓ Flatten outputs removed.$(RESET)"