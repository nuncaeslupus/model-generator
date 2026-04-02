"""
Interactive wizard main menu.
"""

from __future__ import annotations

from .prompts import select

_MENU_CHOICES = [
    "Setup/update project settings",
    "Generate code",
    "Clean generated files",
    "Run tests",
    "Exit",
]


def run_menu() -> None:
    """Main menu loop for the interactive wizard."""
    print("\n=== Model Generator - Interactive Wizard ===\n")

    while True:
        choice = select("What would you like to do?", choices=_MENU_CHOICES)

        if choice == "Exit":
            print("\nGoodbye.")
            break
        elif choice == "Setup/update project settings":
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
