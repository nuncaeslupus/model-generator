"""
Shared output-writing utility for generated files.
"""

from pathlib import Path
from typing import Any


def write_outputs(
    outputs: list[dict[str, Any]], diff: bool, dry_run: bool
) -> list[Path]:
    """Write generator outputs to files, returning list of written paths.

    Supports three write modes via ``output["mode"]``:
    - ``"write"`` (default) — overwrite the file.
    - ``"append"`` — append to an existing file; logs new/skipped counts.
    - ``"skip-if-exists"`` — emit the file once; silently skip on subsequent
      runs so adopters' edits survive regeneration.
    """
    generated_files: list[Path] = []

    for output in outputs:
        path: Path = output["path"]
        content: str = output["content"]
        mode: str = output.get("mode", "write")

        # Customization-seam files are emitted once and never clobbered.
        if mode == "skip-if-exists" and path.exists():
            if not (diff or dry_run):
                print(f"  ℹ️  Exists, skipped: {path}")
            continue

        if diff:
            print(f"\n--- {path} ---")
            if mode == "append":
                print(f"[Would append - {output.get('new_count', 0)} new items]")
            elif path.exists():
                print("[Would update existing file]")
            else:
                print("[Would create new file]")
            print(content[:500] + "..." if len(content) > 500 else content)
            continue

        if dry_run:
            action = "append to" if mode == "append" else "write"
            print(f"  Would {action}: {path}")
            continue

        path.parent.mkdir(parents=True, exist_ok=True)

        if mode == "append":
            with path.open("a", encoding="utf-8") as f:
                f.write(content)
            new_count = output.get("new_count", 0)
            skipped = output.get("skipped", 0)
            print(f"  ✅ Appended {new_count} item(s) to: {path}")
            if skipped > 0:
                print(f"     (skipped {skipped} already existing)")
        else:
            with path.open("w", encoding="utf-8") as f:
                f.write(content)
            print(f"  ✅ Generated: {path}")

        generated_files.append(path)

    return generated_files
