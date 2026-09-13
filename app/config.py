from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel: the shipped placeholder secret. The server refuses to start with it
# (see validate_security / lifespan) so a real deployment cannot run unsigned-safe.
INSECURE_DEFAULT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    storage_root: str = "/data"
    secret_key: str = INSECURE_DEFAULT_SECRET
    jwt_expire_hours: int = 24 * 7
    max_chunk_size_mb: int = 10
    allowed_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def validate_security(self) -> None:
        """Fail fast on an unsafe configuration. Called at startup, not import,
        so tests can import the app and set a secret via env/monkeypatch."""
        if not self.secret_key or self.secret_key == INSECURE_DEFAULT_SECRET:
            raise RuntimeError(
                "SECRET_KEY is unset or still the insecure default. "
                "Set a strong secret before starting, e.g.: openssl rand -hex 32"
            )


settings = Settings()
