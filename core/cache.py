from redis import asyncio as aioredis

from schemas.task_schema import TaskInfoSchema
from settings import settings

# 这里只创建连接池；main.py 的 lifespan 启动时会 ping 一次真正连上，退出时关闭
redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

TASK_PREFIX = "pytask:"
TASK_EXPIRE = 60 * 60


async def set_task_info(task_info: TaskInfoSchema):
    key = f"{TASK_PREFIX}{task_info.task_id}"
    await redis_client.set(key, task_info.model_dump_json(), ex=TASK_EXPIRE)


async def get_task_info(task_id: str) -> TaskInfoSchema | None:
    value = await redis_client.get(f"{TASK_PREFIX}{task_id}")
    if value is None:
        return None
    return TaskInfoSchema.model_validate_json(value)
