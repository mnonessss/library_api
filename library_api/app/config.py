from typing import Optional

from pydantic import model_validator

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DATABASE_URL: Optional[str] = None
    DB_REPLICA_HOST: Optional[str] = None
    DB_REPLICA_PORT: Optional[int] = None
    DATABASE_REPLICA_URL: Optional[str] = None
    ALERT_LOG_PATH: str = 'logs/partition_alerts.log'
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    SHARD_DATABASE_URLS: Optional[str] = None
    SHARD_STRATEGY: str = 'modulo'
    SHARD_VIRTUAL_NODES: int = 128

    @model_validator(mode='after')
    def assemble_database_url(self):
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f'postgresql://{self.DB_USER}:{self.DB_PASSWORD}'
                f'@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}'
            )
        if not self.DATABASE_REPLICA_URL and self.DB_REPLICA_HOST:
            replica_port = self.DB_REPLICA_PORT or 5432
            self.DATABASE_REPLICA_URL = (
                f'postgresql://{self.DB_USER}:{self.DB_PASSWORD}'
                f'@{self.DB_REPLICA_HOST}:{replica_port}/{self.DB_NAME}'
            )
        return self

    @property
    def shard_urls(self) -> list[str]:
        if not self.SHARD_DATABASE_URLS:
            return []
        return [
            url.strip()
            for url in self.SHARD_DATABASE_URLS.split(',')
            if url.strip()
        ]

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'


settings = Settings()
