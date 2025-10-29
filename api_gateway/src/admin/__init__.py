"""Admin package."""

# Do not import submodules here to avoid circular/early import issues during
# Uvicorn reload/spawn on Windows. Import symbols directly from submodules
# where needed, e.g. `from .routes import router`.

__all__ = []
