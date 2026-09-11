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

    @model_validator(mode='after')
    def assemble_database_url(self):
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f'postgresql://{self.DB_USER}:{self.DB_PASSWORD}'
                f'@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}'
            )
        return self

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'


settings = Settings()
