from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Values are read from the .env file in the backend/ directory.
    pydantic-settings automatically maps UPPER_CASE env vars to these fields.
    """

    DATABASE_URL: str

    class Config:
        env_file = ".env"


# Single settings instance used throughout the app
settings = Settings()
