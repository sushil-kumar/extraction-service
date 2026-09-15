from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    max_file_size_mb: int = 10
    log_level: str = "INFO"
    enable_llm_fallback: bool = True

    class Config:
        env_file = ".env"

    @property
    def llm_available(self) -> bool:
        """True only if the LLM fallback is enabled AND a usable API key is present."""
        return self.enable_llm_fallback and bool(self.anthropic_api_key.strip())

settings = Settings()