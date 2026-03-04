"""Environment-based settings for Teams relay backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _load_dotenv_files() -> None:
    """Load .env files near this module with low precedence."""
    base = Path(__file__).resolve().parent
    env_file = (os.environ.get("NANOBOT_ENV_FILE") or "").strip()
    if env_file:
        load_dotenv(env_file, override=False)
        return
    load_dotenv(base / ".env", override=False)
    load_dotenv(base / ".env.local", override=False)


_load_dotenv_files()


def _to_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    port: int
    app_id: str
    app_password: str
    app_type: str
    app_tenant_id: str
    nanobot_inbound_url: str
    nanobot_inbound_host: str
    nanobot_timeout_sec: float
    nanobot_verify_ssl: bool
    internal_token: str
    reference_store_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            port=int(os.environ.get("PORT", "3978")),
            app_id=os.environ.get("MicrosoftAppId", ""),
            app_password=os.environ.get("MicrosoftAppPassword", ""),
            app_type=os.environ.get("MicrosoftAppType", "MultiTenant"),
            app_tenant_id=os.environ.get("MicrosoftAppTenantId", ""),
            nanobot_inbound_url=os.environ.get(
                "NANOBOT_INBOUND_URL",
                "",
            ),
            nanobot_inbound_host=os.environ.get("NANOBOT_INBOUND_HOST", ""),
            nanobot_timeout_sec=float(os.environ.get("NANOBOT_TIMEOUT_SEC", "20")),
            nanobot_verify_ssl=_to_bool(os.environ.get("NANOBOT_VERIFY_SSL"), default=True),
            internal_token=os.environ.get("INTERNAL_TOKEN", ""),
            reference_store_path=Path(
                os.environ.get(
                    "REFERENCE_STORE_PATH",
                    "./data/conversation_references.json",
                )
            ),
        )

    @property
    def APP_ID(self) -> str:
        return self.app_id

    @property
    def APP_PASSWORD(self) -> str:
        return self.app_password

    @property
    def APP_TYPE(self) -> str:
        return self.app_type

    @property
    def APP_TENANTID(self) -> str:
        return self.app_tenant_id
