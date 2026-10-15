"""Settings and constants shared by every pipeline job."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta, timezone
from pathlib import Path

MYT = timezone(timedelta(hours=8), "MYT")
USER_AGENT = "MYHaze/0.1 (+https://github.com/kiizenitc/myhaze)"
REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    aqicn_token: str | None
    db_url: str | None
    firms_key: str | None = None


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ without overriding values already set."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value and key not in os.environ:
            os.environ[key] = value


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or REPO_ROOT / ".env")
    return Settings(
        aqicn_token=os.environ.get("AQICN_TOKEN") or None,
        db_url=os.environ.get("SUPABASE_DB_URL") or None,
        firms_key=os.environ.get("FIRMS_MAP_KEY") or None,
    )
