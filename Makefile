.PHONY: lint format test test-all clean sync build publish publish-force version-sync check-version-sync tag-release update-skills

sync:
	uv sync --extra dev

build:
	rm -rf dist/ && uv run python -m build

# Refuse to upload when the corresponding v* tag already exists on origin —
# .github/workflows/release.yml is the canonical publish path (trusted
# publishing via OIDC) and a local upload would race it and fail with a
# PyPI 400 "File already exists". Use 'make publish-force' to bypass when
# the workflow is unavailable (GitHub Actions outage, broken OIDC config,
# or re-publishing after the workflow failed past the build job).
publish:
	@VER=$$(uv run python -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])"); \
	TAG="v$$VER"; \
	if git ls-remote --exit-code --tags origin "$$TAG" >/dev/null 2>&1; then \
		echo "ERROR: tag $$TAG already exists on origin."; \
		echo "       .github/workflows/release.yml handles PyPI publishing on tag push."; \
		echo "       Running 'twine upload' here would race the workflow and fail."; \
		echo ""; \
		echo "       To bypass (workflow broken / re-publishing after a build-job"; \
		echo "       pass + publish-job fail), run: make publish-force"; \
		echo ""; \
		echo "       See RELEASE.md for the canonical tag/push flow."; \
		exit 1; \
	fi; \
	$(MAKE) publish-force

publish-force: build
	uv run twine upload dist/*

# Cut a release: tag the CURRENT main HEAD with v<pyproject-version> and push,
# which triggers .github/workflows/release.yml (build -> PyPI -> GitHub release).
# Guards make it impossible to tag the wrong commit — the most common release
# mistake. Run this after the version-bump commit has merged to main.
tag-release:
	@VER=$$(uv run python -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])"); \
	TAG="v$$VER"; \
	BRANCH=$$(git rev-parse --abbrev-ref HEAD); \
	if [ "$$BRANCH" != "main" ]; then \
		echo "ERROR: releases are tagged from main, but you are on '$$BRANCH'."; \
		echo "       Run: git checkout main && git pull"; \
		exit 1; \
	fi; \
	if [ -n "$$(git status --porcelain)" ]; then \
		echo "ERROR: working tree is dirty; commit or stash before releasing."; \
		exit 1; \
	fi; \
	git fetch --quiet origin main; \
	if [ "$$(git rev-parse HEAD)" != "$$(git rev-parse origin/main)" ]; then \
		echo "ERROR: local main is not in sync with origin/main."; \
		echo "       The bump commit must be pushed/merged first. Run: git pull"; \
		exit 1; \
	fi; \
	$(MAKE) check-version-sync; \
	if git ls-remote --exit-code --tags origin "$$TAG" >/dev/null 2>&1; then \
		echo "ERROR: tag $$TAG already exists on origin (version $$VER already released?)."; \
		echo "       Bump [project].version, run 'make version-sync', commit, merge, retry."; \
		exit 1; \
	fi; \
	echo "Tagging $$(git rev-parse --short HEAD) on main as $$TAG ..."; \
	git tag -a "$$TAG" -m "model-generator $$TAG"; \
	git push origin "$$TAG"; \
	echo ""; \
	echo "Pushed $$TAG. release.yml will build, publish model-generator-kit==$$VER"; \
	echo "to PyPI, and cut the GitHub release. Watch: gh run watch (or the Actions tab)."

version-sync:
	uv run scripts/sync_version.py

check-version-sync:
	uv run scripts/check_version_sync.py

lint: check-version-sync
	uv run ruff check . && uv run ruff format --check . && uv run mypy . --explicit-package-bases

format:
	uv run ruff check --fix --unsafe-fixes . && uv run ruff format .

test:
	uv run pytest tests/ -m "not slow" -v

test-all:
	uv run pytest tests/ -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .mypy_cache .ruff_cache .pytest_cache dist/

update-skills:
	git subtree pull --prefix .claude/skills https://github.com/nuncaeslupus/my-skills.git main --squash
