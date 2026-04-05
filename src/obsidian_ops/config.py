from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPS_", extra="ignore")

    vault_dir: Path
    site_dir: Path
    vllm_base_url: str = "http://127.0.0.1:8000/v1"
    vllm_model: str = "local-model"
    vllm_api_key: str = ""
    jj_bin: str = "jj"
    kiln_bin: str = "kiln"
    kiln_timeout_s: int = 180
    workers: int = 1
    max_tool_iterations: int = 12
    max_search_results: int = 12
    page_url_prefix: str = "/"
    host: str = "127.0.0.1"
    port: int = 8080

    @field_validator("vault_dir")
    @classmethod
    def validate_vault_dir(cls, value: Path) -> Path:
        resolved = value.expanduser().resolve()
        if not resolved.exists():
            raise ValueError(f"Vault directory does not exist: {resolved}")
        if not resolved.is_dir():
            raise ValueError(f"Vault directory is not a directory: {resolved}")
        return resolved

    @field_validator("site_dir")
    @classmethod
    def validate_site_dir(cls, value: Path) -> Path:
        resolved = value.expanduser().resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
