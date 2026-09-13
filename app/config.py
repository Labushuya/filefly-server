from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    storage_root: str = "/data"
    secret_key: str = "change-me-in-production"
    jwt_expire_hours: int = 24 * 7
    max_chunk_size_mb: int = 10
    admin_invite_code: str = "admin-setup"
    allowed_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
