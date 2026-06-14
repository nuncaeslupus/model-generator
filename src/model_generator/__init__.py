"""Model Generator — one-shot bootstrap code generator for FastAPI backends."""

# Single source of truth is pyproject.toml's [project].version. `make
# version-sync` propagates that value here; `make check-version-sync` (run in
# CI) fails the build if they drift. Do not edit by hand.
__version__ = "0.1.4"
