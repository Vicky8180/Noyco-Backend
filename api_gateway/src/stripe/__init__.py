# Stripe integration package 
# Import settings early – this will raise ValidationError on startup if required
# environment variables (e.g. PRICE_* ids) are missing, ensuring fail-fast.
from .config import get_settings  # noqa: F401

# Initialise settings to trigger validation
_settings = get_settings()

from .routes import router  # noqa 
