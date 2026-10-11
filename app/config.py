from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://payments:payments@localhost:5432/payments"
    rabbit_url: str = "amqp://guest:guest@localhost:5672/"
    api_key: str = "dev-key"


settings = Settings()
