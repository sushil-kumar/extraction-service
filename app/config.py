from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    llm_provider: str = "ollama"  # "anthropic" | "gemini" | "ollama"

    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5vl:7b"
    ollama_keep_alive: str = "30m"

    max_file_size_mb: int = 10
    log_level: str = "INFO"
    enable_llm_fallback: bool = True

    class Config:
        env_file = ".env"

    @property
    def llm_available(self) -> bool:
        if not self.enable_llm_fallback:
            return False
        if self.llm_provider == "gemini":
            return bool(self.gemini_api_key.strip())
        if self.llm_provider == "ollama":
            return True  # no API key needed — just needs Ollama running locally
        return bool(self.anthropic_api_key.strip())

settings = Settings()