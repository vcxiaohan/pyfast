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
    # 后台任务的状态存在 Redis 里
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    # 通义千问（阿里云百炼）的 API Key
    DASHSCOPE_API_KEY: str
    # 中台数据助手连接 MCP 的地址：必须是本机，不能经过负载均衡，否则请求可能被转到别的实例
    MCP_INTERNAL_URL: str = "http://127.0.0.1:8000/ai/mcp"
    # 导出任务队列；线上换成阿里云 RabbitMQ 的 VPC 接入点
    RABBITMQ_URL: str = "amqp://guest:guest@127.0.0.1:5672/"
    # 演示用：worker 每个导出任务额外等这么多秒，数据少时也能看到“生成中”。线上保持 0
    EXPORT_DEMO_DELAY: int = 0
    # 导出的 Excel 存 OSS。AccessKey 用只有 exports/ 目录读写权限的 RAM 子账号，不要用主账号的
    OSS_REGION: str = "cn-hangzhou"
    OSS_BUCKET: str = "oss-next"
    OSS_ACCESS_KEY_ID: str
    OSS_ACCESS_KEY_SECRET: str
    # 部署在同地域的 ECS 上时设为 true，上传走内网
    OSS_INTERNAL: bool = False


settings = Settings()

DB_URI = settings.DB_URI
