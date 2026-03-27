import os

from agents.config import DEFAULT_CONFLICT

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except Exception:  # pragma: no cover - fallback when pydantic-settings is unavailable
    from pydantic import BaseModel

    class BaseSettings(BaseModel):  # type: ignore[misc]
        pass

    SettingsConfigDict = dict  # type: ignore[assignment]


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    auto_analyze_conflict: str = os.getenv("AUTO_ANALYZE_CONFLICT", DEFAULT_CONFLICT)
    auto_analyze_interval_sec: int = int(os.getenv("AUTO_ANALYZE_INTERVAL_SEC", "86400"))
    auto_analyze_timeout_sec: int = int(os.getenv("AUTO_ANALYZE_TIMEOUT_SEC", "300"))

    newsletter_in_process_scheduler: bool = (
        (os.getenv("NEWSLETTER_IN_PROCESS_SCHEDULER", "true") or "").strip().lower() not in ("0", "false", "no")
    )
    newsletter_send_timezone: str = (os.getenv("NEWSLETTER_SEND_TIMEZONE") or "Europe/Berlin").strip() or "Europe/Berlin"
    newsletter_send_hour: int = max(0, min(23, int(os.getenv("NEWSLETTER_SEND_HOUR", "10"))))
    newsletter_send_minute: int = max(0, min(59, int(os.getenv("NEWSLETTER_SEND_MINUTE", "0"))))
    newsletter_reminder_hours: int = max(1, int(os.getenv("NEWSLETTER_REMINDER_HOURS", "6")))
    newsletter_reminder_check_interval_sec: int = max(
        300, int(os.getenv("NEWSLETTER_REMINDER_CHECK_INTERVAL_SEC", "1800"))
    )
    newsletter_reminder_batch_size: int = max(1, min(1000, int(os.getenv("NEWSLETTER_REMINDER_BATCH_SIZE", "100"))))
    retention_enabled: bool = (os.getenv("RETENTION_ENABLED", "true") or "").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    retention_interval_sec: int = max(3600, int(os.getenv("RETENTION_INTERVAL_SEC", "86400")))


settings = AppSettings()
