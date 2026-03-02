from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAISettings(BaseSettings):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = "gpt-4"
    temperature: float = 0
    model_config = SettingsConfigDict(env_prefix="openai_", extra="ignore", env_file=".env")
