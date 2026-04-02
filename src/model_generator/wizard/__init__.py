"""
Interactive wizard for model-generator.

Usage:
    model-gen --interactive
"""

from .menu import run_menu as run_wizard

__all__ = ["run_wizard"]
