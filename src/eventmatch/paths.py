"""Checkout-owned data and .env paths for the editable application package."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"
DEFAULT_CATALOG = ROOT / "data" / "hackathon dataset anonymized .csv"
# Preserve relative overrides (relative to the process working directory).
CATALOG_PATH = Path(os.environ.get("NOVA_DATASET", str(DEFAULT_CATALOG)))
