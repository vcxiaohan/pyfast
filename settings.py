from datetime import timedelta
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 用绝对路径，不管从哪个目录启动都能找到 .env；extra="ignore" 允许 .env 里有用不到的变量
    model_config = SettingsConfigDict(env_file=Path(__file__).parent / ".env", extra="ignore")

    DB_URI: str
    # JWT 签名密钥，泄露了别人就能伪造任意用户的 token，只能放在 .env 里
    JWT_SECRET_KEY: str
    JWT_EXPIRES: timedelta = timedelta(days=1)


settings = Settings()

DB_URI = settings.DB_URI
