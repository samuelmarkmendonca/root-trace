import os
from pathlib import Path
from typing import Any, Dict
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class Settings(BaseSettings):
    prometheus_url: str = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
    loki_url: str = os.getenv("LOKI_URL", "http://loki:3100")
    services_file: str = os.getenv("SERVICES_FILE", "services.yaml")
    max_window_minutes: int = 120
    default_window_minutes: int = 15

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def load_services_config(filepath: str | Path | None = None) -> Dict[str, Any]:
    path = Path(filepath or settings.services_file)
    if not path.is_absolute():
        candidates = [
            path,
            Path(__file__).resolve().parent / path,
            Path(__file__).resolve().parent.parent / path,
            Path("/app") / path,
        ]
        for c in candidates:
            if c.exists():
                path = c
                break

    if not path.exists():
        raise FileNotFoundError(f"Services file not found at {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("services", {})
