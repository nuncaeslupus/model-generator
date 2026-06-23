#!/usr/bin/env bash
#
# Regenerate the flutter-app example into a throwaway tree and verify the
# generated Dart source is valid: dart pub get → build_runner build → dart analyze.
# This is the Flutter stack's analogue of smoke_generated_example.sh.
#
# Requires Flutter SDK on PATH (CI uses subosito/flutter-action@v2).
#
# Usage: scripts/smoke_generated_flutter.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE="$REPO_ROOT/examples/flutter-app"
WORK="$(mktemp -d)"
trap 'cd "$REPO_ROOT" && rm -rf "$WORK"' EXIT

echo "==> Regenerating flutter-app example into $WORK"
cp -r "$EXAMPLE/models" "$WORK/models"
cp "$EXAMPLE/.model-generator.yaml" "$WORK/.model-generator.yaml"

cd "$WORK"
uv run --project "$REPO_ROOT" model-gen models --target all

echo "==> Installing Dart dependencies"
dart pub get

echo "==> Running build_runner (generates .g.dart / .freezed.dart)"
dart run build_runner build

echo "==> Analyzing generated Dart"
dart analyze

echo "==> Flutter smoke test passed"
