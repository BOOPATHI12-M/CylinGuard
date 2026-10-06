"""Centralised application configuration.

Every tunable is read from the environment (or a .env file) exactly once,
here. No module should call os.getenv directly.
"""

from functools import lru_cache
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_name: str = "CylinGuard"
    api_port: int = 8000
    debug: bool = False

    # --- Database ---
    database_url: str = Field(
        default="mysql+pymysql://cylinguard_user:change_me@127.0.0.1:3306/cylinguard"
    )

    # --- Security ---
    jwt_secret: str = Field(default="change_this_secret")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    # NoDecode is required, not cosmetic: pydantic-settings JSON-decodes complex
    # types (List, dict, ...) inside DotEnvSettingsSource *before* any validator
    # runs, so the comma-separated CORS_ORIGINS that .env.example ships would die
    # with a JSONDecodeError before _split_origins below ever saw it. NoDecode
    # hands the raw string to the validator instead.
    cors_origins: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost"]
    )

    # --- Device / IoT ---
    # Optional shared secret the ESP32 sends as X-Device-Key. Blank disables the check.
    device_api_key: str = ""
    device_offline_seconds: int = 120

    # --- Sensor processing ---
    # Weight deltas below this are load-cell noise, not real consumption.
    min_meaningful_delta_kg: float = 0.02
    # A positive weight jump at or above this is a refill, not negative consumption.
    refill_delta_kg: float = 2.0
    smoothing_window: int = 5
    # Physically implausible readings are rejected outright.
    max_plausible_weight_kg: float = 120.0
    max_plausible_gas_value: int = 4095

    # --- Prediction ---
    # Below this many daily consumption records, skip the ML model and use
    # the arithmetic fallback with an honest low-confidence label.
    ml_min_samples: int = 14
    ml_model_path: str = "app/ml/artifacts/predictor.joblib"

    # --- Demo mode ---
    demo_mode_default: bool = True
    demo_tick_seconds: int = 5

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        """Accept a comma-separated string from the environment."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_default_secret(self) -> bool:
        """True when JWT_SECRET was never changed from the shipped placeholder."""
        return self.jwt_secret in ("change_this_secret", "", "secret")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
