"""Environment-based settings for Teams relay backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    port: int
    app_id: str
    app_password: str
    app_type: str
    app_tenant_id: str
    nanobot_inbound_url: str
    nanobot_timeout_sec: float
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
                "http://127.0.0.1:18800/internal/inbound",
            ),
            nanobot_timeout_sec=float(os.environ.get("NANOBOT_TIMEOUT_SEC", "20")),
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
