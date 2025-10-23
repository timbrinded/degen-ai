.PHONY: help
help:
	@echo "Available targets:"
	@echo "  make typecheck    - Run pyrefly type checker"
	@echo "  make lint         - Run ruff linter"
	@echo "  make format       - Run ruff formatter"
	@echo "  make test         - Run pytest"
	@echo "  make test-unit    - Run unit tests only"
	@echo "  make test-int     - Run integration tests only"
	@echo "  make check        - Run all checks (typecheck + lint + test)"
	@echo "  make install-hooks - Install pre-commit hooks"

.PHONY: typecheck
typecheck:
	uv run pyrefly check src/

.PHONY: typecheck-all
typecheck-all:
	uv run pyrefly check

.PHONY: lint
lint:
	uv run ruff check

.PHONY: format
format:
	uv run ruff format

.PHONY: test
test:
	uv run pytest

.PHONY: test-unit
test-unit:
	uv run pytest tests/unit/

.PHONY: test-int
test-int:
	uv run pytest tests/integration/

.PHONY: check
check: typecheck lint test

.PHONY: install-hooks
install-hooks:
	uv run pre-commit install
