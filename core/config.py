from pydantic_settings import SettingsConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    For managing env variables
    """

    DATABASE_URL: str = "sqlite+aiosqlite:///./printpuf.db"
    SQUAD_SECRET_KEY: str = "test_squad_secret"
    SQUAD_BASE_URL: str = "https://squad.example.test"
    DO_SPACES_REGION: str = "fra1"
    DO_SPACES_KEY: str = "test_key"
    DO_SPACES_SECRET: str = "test_secret"
    DO_SPACES_BUCKET: str = "printpuf-test"
    JWT_SECRET_KEY: str = "printpuf-dev-secret"
    JWT_EXPIRES_HOURS: int = 168
    PRINTPUF_ED25519_PRIVATE_KEY_PEM: str | None = None
    PRINTPUF_ED25519_PUBLIC_KEY_PEM: str | None = None
    PRINTPUF_PRIVATE_KEY_PEM: str | None = None
    PRINTPUF_PUBLIC_KEY_PEM: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
