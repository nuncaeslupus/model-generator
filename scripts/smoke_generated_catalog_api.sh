#!/usr/bin/env bash
#
# Regenerate the catalog-api example into a throwaway tree and run its generated
# contract suite end-to-end. Exercises: per-domain layout, api-key auth strategy,
# composite-FK (Warehouse/StockEntry with api.enabled: false), and ProductStatus
# enum from _shared/enums.json.
#
# The generated stack uses PEP 695 generics (`class Paginated[T]`), so the
# example must run under Python 3.12+. We generate with the repo's interpreter
# (version-agnostic) and run the emitted suite in a dedicated 3.12 venv.
#
# Usage: scripts/smoke_generated_catalog_api.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE="$REPO_ROOT/examples/catalog-api"
WORK="$(mktemp -d)"
trap 'cd "$REPO_ROOT" && rm -rf "$WORK"' EXIT

echo "==> Regenerating catalog-api example into $WORK"
cp -r "$EXAMPLE/models" "$WORK/models"
cp "$EXAMPLE/.model-generator.yaml" "$WORK/.model-generator.yaml"

# model-gen reads .model-generator.yaml from the CWD, so generate from inside
# the work tree (a repo-root invocation would silently drop the project config).
cd "$WORK"
uv run --project "$REPO_ROOT" model-gen models --target all

echo "==> Installing generated project (Python 3.12)"
uv venv --python 3.12 .venv
uv pip install --python .venv -e ".[dev]"

echo "==> Running generated contract suite"
.venv/bin/python -m pytest -q

echo "==> Generated catalog-api suite passed"
