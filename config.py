from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "RFP Intelligence System"
    VERSION: str = "1.0.0"
    DATABASE_URL: str = "sqlite:///./rfp_intelligence.db"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    SERPAPI_KEY: str = ""
    LLM_PROVIDER: str = "groq"
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ALERT_EMAIL_TO: str = "rfp-alerts@eaisystems.com"
    MATCH_SCORE_THRESHOLD: int = 70
    HIGH_PRIORITY_SCORE: int = 85

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
