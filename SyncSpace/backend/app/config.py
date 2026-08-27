from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Values are read from the .env file in the backend/ directory.
    pydantic-settings automatically maps UPPER_CASE env vars to these fields.
    """

    DATABASE_URL: str
    JWT_SECRET_KEY: str = "default_development_secret_key_change_me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Single settings instance used throughout the app
settings = Settings()
