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

    # Phase 5 & 6: Knowledge Base, Vector Embeddings & RAG
    GEMINI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"
    EMBEDDING_DIMENSION: int = 768
    LLM_MODEL: str = "gemini-2.5-flash"
    RAG_TOP_K: int = 5
    MAX_QUESTION_LENGTH: int = 1000
    MAX_FILE_SIZE_MB: int = 15
    UPLOAD_DIR: str = "uploads"
    CHUNK_SIZE_TOKENS: int = 600
    CHUNK_OVERLAP_TOKENS: int = 100

    @property
    def effective_gemini_api_key(self) -> str:
        """Returns GEMINI_API_KEY or GOOGLE_API_KEY if available."""
        return self.GEMINI_API_KEY or self.GOOGLE_API_KEY

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Single settings instance used throughout the app
settings = Settings()

