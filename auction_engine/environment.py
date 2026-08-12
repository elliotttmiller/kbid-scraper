from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
FALSE_VALUES = {"0", "false", "no", "off"}


def load_workspace_environment() -> None:
    """Load local secrets without overriding explicitly exported variables."""
    local_file = WORKSPACE_ROOT / ".env.local"
    fallback_file = WORKSPACE_ROOT / ".env"
    if local_file.is_file():
        load_dotenv(local_file, override=False)
    elif fallback_file.is_file():
        load_dotenv(fallback_file, override=False)


def feature_explicitly_disabled(name: str) -> bool:
    value = os.getenv(name)
    return value is not None and value.strip().lower() in FALSE_VALUES
