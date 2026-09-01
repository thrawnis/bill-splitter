from urllib.parse import quote_plus

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    postgres_user: str = "billsplit"
    postgres_password: str = ""
    postgres_db: str = "billsplit"
    postgres_host: str = "db"
    postgres_port: int = 5432
    secret_key: str
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2-vision"
    upload_dir: str = "/app/data/uploads"
    session_expire_days: int = 30
    secure_cookies: bool = True

    # Absolute URL of the deployed app, used to build links in emails.
    # Falls back to the incoming request URL when empty.
    app_base_url: str = ""

    # SMTP for emailing payment requests (optional).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql://{self.postgres_user}:{quote_plus(self.postgres_password)}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
