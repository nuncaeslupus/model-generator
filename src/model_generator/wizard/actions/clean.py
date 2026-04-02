"""
Action: Clean generated files.
"""

from __future__ import annotations

from pathlib import Path

from ..prompts import confirm, select


def _find_project_root() -> Path:
    """Find project root by looking for .model-generator.yaml."""
    cwd = Path.cwd()
    if (cwd / ".model-generator.yaml").exists():
        return cwd
    parent = cwd.parent
    if (parent / ".model-generator.yaml").exists():
        return parent
    return cwd


def run_clean() -> None:
    """Select scope, preview, confirm, and clean generated files."""
    project_root = _find_project_root()

    if not (project_root / ".model-generator.yaml").exists():
        print("\nNo .model-generator.yaml found.")
        print("Run 'Setup/update project settings' first.")
        return

    scope = select(
        "Cleanup scope:",
        choices=["selective", "full"],
        default="selective",
    )

    print(f"\nScope: {scope}")
    if scope == "selective":
        print("  Will remove only files that would be regenerated.")
    else:
        print("  Will remove all generated directories, caches, and venvs.")

    # Dry run first
    from ...generate import cleanup_generated

    print("\nPreview (what would be deleted):")
    cleanup_generated(project_root, scope=scope, dry_run=True)

    if not confirm("\nProceed with deletion?", default=False):
        print("Cancelled.")
        return

    cleanup_generated(project_root, scope=scope, dry_run=False)
    print("\nCleanup complete.")
