"""
Interactive wizard main menu.
"""

from __future__ import annotations

from .prompts import PromptCancelled, select

_MENU_CHOICES = [
    "Setup/update project settings",
    "Generate code",
    "Clean generated files",
    "Run tests",
    "Exit",
]


def run_menu() -> None:
    """Main menu loop for the interactive wizard.

    A cancelled top-level prompt (Ctrl-C / ESC) exits the wizard; a cancelled
    prompt inside an action aborts that action and returns to the menu.
    """
    print("\n=== Model Generator - Interactive Wizard ===\n")

    while True:
        try:
            choice = select("What would you like to do?", choices=_MENU_CHOICES)
        except (PromptCancelled, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if choice == "Exit":
            print("\nGoodbye.")
            break

        try:
            _dispatch(choice)
        except (PromptCancelled, KeyboardInterrupt):
            print("\nCancelled. Returning to menu.")


def _dispatch(choice: str) -> None:
    """Run the action for a menu choice."""
    if choice == "Setup/update project settings":
        from .actions.project_setup import run_setup

        run_setup()
    elif choice == "Generate code":
        from .actions.generate import run_generate

        run_generate()
    elif choice == "Clean generated files":
        from .actions.clean import run_clean

        run_clean()
    elif choice == "Run tests":
        from .actions.test_runner import run_tests

        run_tests()
