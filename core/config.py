from pydantic_settings import SettingsConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    For managing env variables
    """

    DATABASE_URL: str
    CLERK_WEBHOOK_SECRET: str
    CLERK_FRONTEND_API_URL: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
