from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LAB_TUTOR_",
        extra="ignore",
    )

    app_name: str = "Lab Tutor Backend"
    secret_key: str = Field(
        "change-this-secret",
        description="JWT signing secret. Override in production via LAB_TUTOR_SECRET_KEY.",
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    database_url: str = Field(
        default="sqlite:///./data/app.db",
        description="SQLAlchemy database URL",
    )


settings = Settings()
