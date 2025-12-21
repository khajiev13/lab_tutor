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
    azure_storage_connection_string: str | None = Field(
        default=None, description="Azure Blob Storage Connection String"
    )
    azure_container_name: str = Field(
        default="class-presentations", description="Container name for presentations"
    )

    # Neo4j (Knowledge Graph)
    neo4j_uri: str | None = Field(default=None, description="Neo4j URI")
    neo4j_username: str | None = Field(default=None, description="Neo4j username")
    neo4j_password: str | None = Field(default=None, description="Neo4j password")
    neo4j_database: str = Field(default="neo4j", description="Neo4j database name")


settings = Settings()
