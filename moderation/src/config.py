import os


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://neomarket:neomarket_dev_2026@localhost:5432/neomarket_moderation",
    )
    review_timeout_minutes: int = int(os.getenv("REVIEW_TIMEOUT_MINUTES", "30"))


settings = Settings()


def get_settings() -> Settings:
    return settings
