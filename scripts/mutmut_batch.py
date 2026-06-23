#!/usr/bin/env python3
"""
Mutmut batch runner — per-module mutation testing with cross-session progress tracking.

Usage:
    uv run python scripts/mutmut_batch.py --setup
        Generate mutants/ workspace and pre-commit mutant name lists to
        status/mutmut-names.json. Run once per source revision.

    uv run python scripts/mutmut_batch.py --list
        Show all batches with total / killed / survived / pending counts.

    uv run python scripts/mutmut_batch.py --run BATCH [--max-children N]
        Run the pending mutants for BATCH. Pass names directly to mutmut so
        only that batch is tested. Requires mutants/ workspace (auto-creates
        it if missing via --setup).

    uv run python scripts/mutmut_batch.py --update
        Refresh status/mutmut-progress.json from current .meta files.

    uv run python scripts/mutmut_batch.py --cmd BATCH
        Print the raw mutmut run command (useful for backgrounding manually).

Cross-session workflow
----------------------
1. Run --setup once. Commits status/mutmut-names.json.
2. Each session: --run BATCH-N (in background or foreground), then --update, commit.
3. Next session: --list shows remaining work; container may be recycled but
   mutants/ is regenerated deterministically from the committed source.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
from typing import Any

ROOT = pathlib.Path(__file__).parent.parent
PROGRESS_FILE = ROOT / "status" / "mutmut-progress.json"
NAMES_FILE = ROOT / "status" / "mutmut-names.json"
MUTANTS_DIR = ROOT / "mutants"

# ---------------------------------------------------------------------------
# Batch definitions — ordered from smallest to largest
# ---------------------------------------------------------------------------

BATCHES: dict[str, list[str]] = {
    "batch-1-utils": [
        "src/model_generator/generators/enums.py",
        "src/model_generator/generators/migrations.py",
        "src/model_generator/generators/registry.py",
        "src/model_generator/utils/output.py",
        "src/model_generator/utils/parser.py",
        "src/model_generator/utils/templates.py",
        "src/model_generator/utils/quality.py",
        "src/model_generator/validate.py",
        "src/model_generator/wizard/actions/_common.py",
        "src/model_generator/wizard/actions/clean.py",
        "src/model_generator/wizard/actions/test_runner.py",
        "src/model_generator/wizard/menu.py",
        "src/model_generator/wizard/prompts.py",
        "src/model_generator/generators/flutter/__init__.py",
        "src/model_generator/generators/flutter/paths.py",
    ],
    "batch-2-generators": [
        "src/model_generator/generators/api.py",
        "src/model_generator/generators/constraints.py",
        "src/model_generator/generators/database.py",
        "src/model_generator/utils/loaders.py",
        "src/model_generator/wizard/actions/generate.py",
        "src/model_generator/wizard/actions/project_setup.py",
    ],
    "batch-3-conftest": [
        "src/model_generator/utils/conftest_generator.py",
    ],
    "batch-4-flutter-api": [
        "src/model_generator/generators/flutter/api.py",
        "src/model_generator/generators/flutter/fields.py",
    ],
    "batch-5-flutter-gen": [
        "src/model_generator/generators/flutter/generators.py",
    ],
    "batch-6-generate": [
        "src/model_generator/generate.py",
    ],
    "batch-7-infrastructure": [
        "src/model_generator/generators/infrastructure.py",
    ],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def meta_file(src: str) -> pathlib.Path:
    return MUTANTS_DIR / f"{src}.meta"


def read_meta(src: str) -> dict[str, Any]:
    p = meta_file(src)
    if not p.exists():
        return {}
    result: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    return result


def pending_names_from_meta(src: str) -> list[str]:
    data = read_meta(src)
    return [k for k, v in data.get("exit_code_by_key", {}).items() if v is None]


def all_names_from_meta(src: str) -> list[str]:
    data = read_meta(src)
    return list(data.get("exit_code_by_key", {}).keys())


def load_names() -> dict[str, list[str]]:
    if NAMES_FILE.exists():
        data: dict[str, list[str]] = json.loads(NAMES_FILE.read_text(encoding="utf-8"))
        return data
    return {}


def load_progress() -> dict[str, Any]:
    if PROGRESS_FILE.exists():
        data: dict[str, Any] = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        return data
    return {"batches": {}}


def batch_stats_from_meta(batch: str) -> dict[str, int]:
    total = killed = survived = pending = 0
    for f in BATCHES.get(batch, []):
        codes = read_meta(f).get("exit_code_by_key", {})
        total += len(codes)
        killed += sum(1 for v in codes.values() if v is not None and v != 0)
        survived += sum(1 for v in codes.values() if v == 0)
        pending += sum(1 for v in codes.values() if v is None)
    return {"total": total, "killed": killed, "survived": survived, "pending": pending}


def ensure_workspace(verbose: bool = True) -> None:
    """Create mutants/ workspace if it doesn't exist or has no .meta files."""
    has_meta = MUTANTS_DIR.exists() and any(MUTANTS_DIR.rglob("*.meta"))
    if has_meta:
        if verbose:
            print("mutants/ workspace already present.")
        return
    if verbose:
        print("mutants/ workspace missing — generating (takes ~20-30s)...")

    # Run mutmut with a hard timeout. Generation takes ~20s; we kill after 35s
    # which is deep into the "Running stats" phase but all .meta files exist.
    try:
        result = subprocess.run(
            ["uv", "run", "mutmut", "run"],
            timeout=35,
            cwd=ROOT,
        )
        if result.returncode != 0:
            print(f"mutmut setup failed (exit {result.returncode}).")
            sys.exit(result.returncode)
    except subprocess.TimeoutExpired:
        pass  # expected — generation done, killed mid-stats

    n_meta = sum(1 for _ in MUTANTS_DIR.rglob("*.meta"))
    if verbose:
        print(f"Workspace ready — {n_meta} .meta files.")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_setup(args: argparse.Namespace) -> None:
    """Generate workspace and persist all mutant names to status/mutmut-names.json."""
    ensure_workspace(verbose=True)

    names: dict[str, list[str]] = {}
    total = 0
    for batch, files in BATCHES.items():
        batch_names: list[str] = []
        for f in files:
            file_names = all_names_from_meta(f)
            batch_names.extend(file_names)
            total += len(file_names)
        names[batch] = batch_names
        print(f"  {batch}: {len(batch_names)} mutants")

    NAMES_FILE.write_text(json.dumps(names, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved {total} mutant names → {NAMES_FILE.relative_to(ROOT)}")
    print(
        "Commit this file so future sessions can regenerate the workspace "
        "and know which names to run without needing the prior mutants/."
    )


def cmd_list(args: argparse.Namespace) -> None:
    """List batches with counts from .meta files (if present) or names file."""
    progress = load_progress()
    saved_names = load_names()

    print(
        f"\n{'Batch':<28} {'Total':>6} {'Killed':>7}"
        f" {'Survived':>9} {'Pending':>8}  Status"
    )
    print("-" * 72)
    gt = gk = gs = gp = 0
    for batch in BATCHES:
        if MUTANTS_DIR.exists() and any(MUTANTS_DIR.rglob("*.meta")):
            s = batch_stats_from_meta(batch)
        else:
            # Fall back to committed names file (no result data yet)
            n = len(saved_names.get(batch, []))
            s = {"total": n, "killed": 0, "survived": 0, "pending": n}

        gt += s["total"]
        gk += s["killed"]
        gs += s["survived"]
        gp += s["pending"]
        status = progress.get("batches", {}).get(batch, {}).get("status", "—")
        marker = "✓" if status == "complete" else " "
        print(
            f"{marker} {batch:<26} {s['total']:>6} {s['killed']:>7} {s['survived']:>9}"
            f" {s['pending']:>8}  {status}"
        )
    print("-" * 72)
    print(f"  {'TOTAL':<26} {gt:>6} {gk:>7} {gs:>9} {gp:>8}")
    print()


def cmd_run(args: argparse.Namespace) -> None:
    """Run pending mutants for one batch."""
    batch = args.batch
    if batch not in BATCHES:
        print(f"Unknown batch '{batch}'. Known batches: {list(BATCHES)}")
        sys.exit(1)

    # Ensure workspace exists
    ensure_workspace(verbose=True)

    # Get names to run: prefer live .meta pending, fall back to committed names
    if any(MUTANTS_DIR.rglob("*.meta")):
        names: list[str] = []
        for f in BATCHES[batch]:
            pn = pending_names_from_meta(f)
            print(f"  {f}: {len(pn)} pending")
            names.extend(pn)
        source = "live .meta"
    else:
        saved = load_names()
        names = saved.get(batch, [])
        source = "committed names"
        print(f"  (using {source}: {len(names)} names)")

    if not names:
        print(f"\nNo pending mutants in {batch}. Already complete?")
        return

    print(f"\n{len(names)} mutants to test ({source}) — starting mutmut run...")
    cmd = ["uv", "run", "mutmut", "run", f"--max-children={args.max_children}", *names]

    if args.cmd_only:
        print("\nCommand (for manual backgrounding):")
        print(" ".join(cmd[:6]) + f" <{len(names)} names...>")
        cmd_path = pathlib.Path(tempfile.gettempdir()) / "mutmut-cmd.sh"
        cmd_path.write_text("#!/bin/bash\n" + " ".join(cmd) + "\n", encoding="utf-8")
        print(f"\nFull command saved to {cmd_path}")
        return

    result = subprocess.run(cmd, cwd=ROOT)
    print(f"\nmutmut exited with code {result.returncode}")
    _update_progress()
    if result.returncode != 0:
        sys.exit(result.returncode)


def cmd_update(_args: Any = None) -> None:
    """Refresh status/mutmut-progress.json from .meta files."""
    _update_progress()
    cmd_list(_args or argparse.Namespace(batch=None))


def _update_progress() -> None:
    progress = load_progress()
    for batch in BATCHES:
        s = batch_stats_from_meta(batch)
        if s["total"] == 0:
            continue
        if s["pending"] == 0:
            status = "complete"
        elif s["killed"] + s["survived"] > 0:
            status = "partial"
        else:
            status = "pending"
        progress["batches"][batch] = {"status": status, **s}
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {PROGRESS_FILE.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mutmut batch runner with cross-session progress tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Generate workspace and commit mutant name lists",
    )
    parser.add_argument(
        "--list", action="store_true", help="Show all batches with counts and status"
    )
    parser.add_argument(
        "--run", metavar="BATCH", dest="batch", help="Run pending mutants for BATCH"
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Refresh status/mutmut-progress.json from .meta files",
    )
    parser.add_argument(
        "--cmd",
        metavar="BATCH",
        dest="cmd_batch",
        help="Print run command for BATCH (for manual backgrounding)",
    )
    parser.add_argument(
        "--max-children",
        type=int,
        default=4,
        help="Parallel mutmut workers (default: 4)",
    )
    parser.add_argument(
        "--cmd-only",
        action="store_true",
        help="With --run: print command instead of running it",
    )
    args = parser.parse_args()

    if args.setup:
        cmd_setup(args)
    elif args.list:
        cmd_list(args)
    elif args.batch:
        cmd_run(args)
    elif args.update:
        cmd_update(args)
    elif args.cmd_batch:
        args.batch = args.cmd_batch
        args.cmd_only = True
        cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
