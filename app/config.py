from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2-vision"
    upload_dir: str = "/app/data/uploads"
    session_expire_days: int = 30
    secure_cookies: bool = True

    model_config = {"env_file": ".env"}


settings = Settings()
