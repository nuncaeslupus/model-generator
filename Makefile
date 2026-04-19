.PHONY: lint format test test-all clean sync update-skills

sync:
	uv sync --extra dev

lint:
	uv run ruff check . && uv run mypy . --explicit-package-bases

format:
	uv run ruff check --fix --unsafe-fixes . && uv run ruff format .

test:
	uv run pytest tests/ -m "not slow" -v

test-all:
	uv run pytest tests/ -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .mypy_cache .ruff_cache .pytest_cache

update-skills:
	git subtree pull --prefix .claude/skills https://github.com/nuncaeslupus/my-skills.git main --squash
