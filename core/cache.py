import json
import logging

from redis import asyncio as aioredis

from schemas.task_schema import TaskInfoSchema
from settings import settings

logger = logging.getLogger(__name__)

# 这里只创建连接池；main.py 的 lifespan 启动时会 ping 一次真正连上，退出时关闭
redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

TASK_PREFIX = "pytask:"
TASK_EXPIRE = 60 * 60

# 导出进度是临时数据，任务结束就没用了：放 Redis 不用改表结构，每页更新一次也不给数据库加写压力，过期自动清理。
# 任务状态和结果仍然以数据库为准
EXPORT_PROGRESS_PREFIX = "export:progress:"


async def set_task_info(task_info: TaskInfoSchema):
    key = f"{TASK_PREFIX}{task_info.task_id}"
    await redis_client.set(key, task_info.model_dump_json(), ex=TASK_EXPIRE)


async def get_task_info(task_id: str) -> TaskInfoSchema | None:
    value = await redis_client.get(f"{TASK_PREFIX}{task_id}")
    if value is None:
        return None
    return TaskInfoSchema.model_validate_json(value)


async def set_export_progress(task_id: str, percent: int, stage: str) -> None:
    try:
        value = json.dumps({"percent": percent, "stage": stage}, ensure_ascii=False)
        await redis_client.set(f"{EXPORT_PROGRESS_PREFIX}{task_id}", value, ex=TASK_EXPIRE)
    except Exception:
        # 进度只是体验优化，Redis 出问题时不能让导出跟着失败
        logger.warning("写导出进度失败：%s", task_id, exc_info=True)


async def get_export_progress(task_id: str) -> dict | None:
    try:
        value = await redis_client.get(f"{EXPORT_PROGRESS_PREFIX}{task_id}")
    except Exception:
        logger.warning("读导出进度失败：%s", task_id, exc_info=True)
        return None
    return json.loads(value) if value else None
