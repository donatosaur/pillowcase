# Author:      Donato Quartuccia
# Modified:    2022-02-22
# Description: App-wide dependencies

from pydantic import BaseSettings
from functools import cache


@cache
def get_env():
    """Loads and caches environment variables"""
    class Settings(BaseSettings):
        HOST: str = "localhost"
        PORT: int = 8000
        DEBUG: bool = False
        IMAGE_DIRECTORY: str

        class Config:
            env_file = ".env"

    return Settings()
