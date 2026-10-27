import os
from pathlib import Path
from typing import Any, Dict
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class Settings(BaseSettings):
    prometheus_url: str = "http://prometheus:9090"
    loki_url: str = "http://loki:3100"
    services_file: str = "services.yaml"
    deploys_file: str = "data/deploys.json"
    max_window_minutes: int = 120
    default_window_minutes: int = 15

    # LLM Agent configuration
    llm_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:7b-8k"
    llm_api_key: str = "ollama"
    llm_temperature: float = 0.1
    llm_max_steps: int = 6

    def get_llm_url(self) -> str:
        if (Path("/.dockerenv").exists() or os.getenv("DOCKER_CONTAINER")) and ("localhost" in self.llm_url or "127.0.0.1" in self.llm_url):
            return self.llm_url.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
        return self.llm_url

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def load_services_config(filepath: str | Path | None = None) -> Dict[str, Any]:
    path = Path(filepath or settings.services_file)
    if not path.is_absolute():
        candidates = [
            path,
            Path(path.name),
            Path(__file__).resolve().parent / path,
            Path(__file__).resolve().parent.parent / path,
            Path(__file__).resolve().parent.parent / path.name,
            Path(__file__).resolve().parent.parent.parent / path,
            Path("/app") / path,
            Path("/app") / path.name,
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


def load_deploys(filepath: str | Path | None = None) -> list[Dict[str, Any]]:
    import json
    path = Path(filepath or settings.deploys_file)
    if not path.is_absolute():
        candidates = [
            path,
            Path(__file__).resolve().parent / path,
            Path(__file__).resolve().parent.parent / path,
            Path(__file__).resolve().parent.parent.parent / path,
            Path("/data/deploys.json"),
        ]
        for c in candidates:
            if c.exists():
                path = c
                break

    if not path.exists():
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    except Exception:
        return []
