"""Model Generator — one-shot bootstrap code generator for FastAPI backends."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("model-generator-kit")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
