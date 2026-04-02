"""
Prompt abstraction for the interactive wizard.

Uses questionary for rich UI if available, falls back to plain input.
"""

from __future__ import annotations

from typing import cast

import questionary as _questionary


def select(message: str, choices: list[str], default: str | None = None) -> str:
    """Show a single-select menu. Returns the chosen string."""
    if _questionary is not None:
        return cast(
            str, _questionary.select(message, choices=choices, default=default).ask()
        )

    # Plain fallback
    print(f"\n{message}")
    for i, choice in enumerate(choices, 1):
        marker = " *" if choice == default else ""
        print(f"  {i}. {choice}{marker}")

    while True:
        raw = input(f"Enter choice (1-{len(choices)}): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        print(f"  Invalid choice. Enter a number 1-{len(choices)}.")


def checkbox(message: str, choices: list[str]) -> list[str]:
    """Show a multi-select checklist. Returns list of selected strings."""
    if _questionary is not None:
        return cast(list[str], _questionary.checkbox(message, choices=choices).ask())

    # Plain fallback
    print(f"\n{message}")
    for i, choice in enumerate(choices, 1):
        print(f"  {i}. {choice}")

    print("Enter choices separated by commas (e.g. 1,3,5), or 'all':")
    while True:
        raw = input("> ").strip()
        if raw.lower() == "all":
            return list(choices)
        try:
            indices = [int(x.strip()) for x in raw.split(",")]
            if all(1 <= i <= len(choices) for i in indices):
                return [choices[i - 1] for i in indices]
        except ValueError:
            pass
        n = len(choices)
        print(f"  Invalid input. Use comma-separated numbers 1-{n}, or 'all'.")


def confirm(message: str, default: bool = True) -> bool:
    """Ask a yes/no question. Returns bool."""
    if _questionary is not None:
        return cast(bool, _questionary.confirm(message, default=default).ask())

    # Plain fallback
    suffix = " [Y/n]" if default else " [y/N]"
    raw = input(f"\n{message}{suffix}: ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes")


def text(message: str, default: str = "") -> str:
    """Ask for text input. Returns string."""
    if _questionary is not None:
        return cast(str, _questionary.text(message, default=default).ask())

    # Plain fallback
    suffix = f" [{default}]" if default else ""
    raw = input(f"\n{message}{suffix}: ").strip()
    return raw if raw else default
