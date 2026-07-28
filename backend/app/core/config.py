"""Application configuration (12-factor style, env driven)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- General -----------------------------------------------------
    APP_NAME: str = "Gozaresh — Enterprise Reporting Platform"
    ENV: Literal["dev", "staging", "prod", "test"] = "dev"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    BASE_CURRENCY: str = "IRR"

    # ---- Security ----------------------------------------------------
    SECRET_KEY: str = "dev-only-insecure-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_MINUTES: int = 30
    REFRESH_TOKEN_TTL_MINUTES: int = 60 * 24 * 7
    PASSWORD_MIN_LENGTH: int = 10
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_MINUTES: int = 15
    RATE_LIMIT_PER_MINUTE: int = 240
    KEYSTORE_DIR: str = "./.keystore"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ---- Database ----------------------------------------------------
    DATABASE_URL: str = "sqlite:///./gozaresh.db"
    SQL_ECHO: bool = False

    # ---- FX / Rates --------------------------------------------------
    FX_PRIMARY_PROVIDER: str = "central_bank"
    FX_FALLBACK_PROVIDER: str = "exchange_api"
    FX_CACHE_TTL_SECONDS: int = 300
    FX_HTTP_TIMEOUT_SECONDS: float = 2.5
    FX_CENTRAL_BANK_URL: str = "https://api.example-cbi.ir/v1/rates"
    FX_EXCHANGE_API_URL: str = "https://api.exchangerate.host/latest"
    FX_OFFLINE_MODE: bool = True  # deterministic fixtures; no outbound calls

    # ---- Calculation SLA ---------------------------------------------
    DECIMAL_PLACES: int = 16
    DECIMAL_PRECISION: int = 60  # headroom: 14+ integer digits (IRR) x 16 dp needs >34
    CALC_SLA_MS: float = 50.0

    # ---- Notifications ------------------------------------------------
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    MAIL_FROM: str = "no-reply@gozaresh-demo.com"
    SMS_PROVIDER_URL: str = "https://api.example-sms.ir/v1/send"
    SMS_API_KEY: str = ""
    NOTIFICATIONS_DRY_RUN: bool = True  # print instead of sending

    # ---- Integrations --------------------------------------------------
    MOADIAN_BASE_URL: str = "https://tp.tax.gov.ir/req/api/self-tsp"
    MOADIAN_MEMORY_ID: str = "DEMO-MEMORY-ID"
    MOADIAN_ECONOMIC_CODE: str = "DEMO-ECONOMIC-CODE"
    BANK_GATEWAY_URL: str = "https://api.example-bank.ir/v1"
    BANK_TERMINAL_ID: str = "DEMO-TERMINAL"
    INTEGRATIONS_SANDBOX: bool = True

    # ---- Alerting -------------------------------------------------------
    ALERT_SCAN_INTERVAL_SECONDS: int = 60
    ANOMALY_ZSCORE_THRESHOLD: float = 3.0
    OVERDUE_GRACE_DAYS: int = 0
    ENABLE_BACKGROUND_SCHEDULER: bool = True

    @field_validator("BASE_CURRENCY")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.ENV == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
