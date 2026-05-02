from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./stratosteam.db"
    api_key: str = "change-me-in-production"
    # For PostgreSQL in production:
    # database_url: str = "postgresql+asyncpg://user:pass@localhost/stratosteam"

    class Config:
        env_file = ".env"


settings = Settings()
