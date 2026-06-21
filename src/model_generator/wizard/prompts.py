"""
Prompt abstraction for the interactive wizard.

Uses questionary for rich UI if available, falls back to plain input.

``questionary`` ships in the optional ``[interactive]`` extra, so the import is
guarded: on a base install ``_questionary`` is ``None`` and every helper uses the
plain ``input()`` fallback. When the user aborts a prompt (Ctrl-C / ESC, or
Ctrl-D at the fallback), the helpers raise :class:`PromptCancelled` instead of
returning ``None`` — questionary's ``.ask()`` returns ``None`` on abort, which
would otherwise propagate as a bogus value (silent re-prompt loops, or a
``TypeError`` when a caller iterates the checkbox result).
"""

from __future__ import annotations

from typing import cast

try:
    import questionary as _questionary
except ImportError:  # pragma: no cover - exercised on a base (no-extras) install
    _questionary = None  # type: ignore[assignment]


class PromptCancelled(Exception):
    """Raised when the user aborts a prompt (Ctrl-C / ESC / Ctrl-D)."""


def select(message: str, choices: list[str], default: str | None = None) -> str:
    """Show a single-select menu. Returns the chosen string."""
    if _questionary is not None:
        answer = _questionary.select(message, choices=choices, default=default).ask()
        if answer is None:
            raise PromptCancelled
        return cast(str, answer)

    # Plain fallback
    print(f"\n{message}")
    for i, choice in enumerate(choices, 1):
        marker = " *" if choice == default else ""
        print(f"  {i}. {choice}{marker}")

    while True:
        raw = _input(f"Enter choice (1-{len(choices)}): ")
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        print(f"  Invalid choice. Enter a number 1-{len(choices)}.")


def checkbox(message: str, choices: list[str]) -> list[str]:
    """Show a multi-select checklist. Returns list of selected strings."""
    if _questionary is not None:
        answer = _questionary.checkbox(message, choices=choices).ask()
        if answer is None:
            raise PromptCancelled
        return cast(list[str], answer)

    # Plain fallback
    print(f"\n{message}")
    for i, choice in enumerate(choices, 1):
        print(f"  {i}. {choice}")

    print("Enter choices separated by commas (e.g. 1,3,5), or 'all':")
    while True:
        raw = _input("> ")
        if not raw:
            # Empty input = no selection, matching questionary.checkbox's [] return
            # (otherwise "".split(",") -> [""] would ValueError-loop forever).
            return []
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
        answer = _questionary.confirm(message, default=default).ask()
        if answer is None:
            raise PromptCancelled
        return cast(bool, answer)

    # Plain fallback
    suffix = " [Y/n]" if default else " [y/N]"
    raw = _input(f"\n{message}{suffix}: ").lower()
    if not raw:
        return default
    return raw in ("y", "yes")


def text(message: str, default: str = "") -> str:
    """Ask for text input. Returns string."""
    if _questionary is not None:
        answer = _questionary.text(message, default=default).ask()
        if answer is None:
            raise PromptCancelled
        return cast(str, answer)

    # Plain fallback
    suffix = f" [{default}]" if default else ""
    raw = _input(f"\n{message}{suffix}: ")
    return raw if raw else default


def _input(prompt: str) -> str:
    """``input()`` that maps Ctrl-D (EOF) to :class:`PromptCancelled`.

    Ctrl-C already raises ``KeyboardInterrupt``, which the menu loop treats the
    same way; mapping EOF here gives the fallback parity with questionary's
    abort-returns-``None`` behaviour.
    """
    try:
        return input(prompt).strip()
    except EOFError as exc:
        raise PromptCancelled from exc
