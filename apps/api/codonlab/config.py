"""Runtime configuration, read from the environment.

Deliberately plain ``os.environ`` rather than pydantic-settings: that would be a
dependency beyond the agreed stack, and this module needs to do very little.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

# Host port 5433, matching docker-compose.yml. Inside the compose network the
# api service is given an explicit DATABASE_URL pointing at postgres:5432.
DEFAULT_DATABASE_URL = "postgresql+psycopg://codonlab:codonlab@localhost:5433/codonlab"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def _split(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    redis_url: str
    cors_origins: tuple[str, ...]
    providers: tuple[str, ...]

    @property
    def demo_mode(self) -> bool:
        """True when any configured provider fabricates numbers.

        When this is set the product must render the persistent amber
        'Demo data — not model output' bar on every screen, badge every number the
        mock produced, watermark exports, and refuse to generate primers.
        """
        return "mock" in self.providers


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        redis_url=os.environ.get("REDIS_URL", DEFAULT_REDIS_URL),
        cors_origins=_split(os.environ.get("CORS_ORIGINS", "http://localhost:3000")),
        providers=_split(os.environ.get("CODONLAB_PROVIDERS", "mock")),
    )
