"""Stripe integration package.

Keep this __init__ lightweight to avoid circular imports and early environment
validation. Import specific symbols from submodules where needed, e.g.:
`from .routes import router`.
"""

__all__ = []
