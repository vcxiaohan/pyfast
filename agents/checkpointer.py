"""对话记忆存 Postgres：API 进程和 worker 进程按 thread_id 读写同一份对话历史，服务重启也不会丢。"""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from settings import DB_URI

pool = AsyncConnectionPool(
    # DB_URI 是 SQLAlchemy 的写法（postgresql+psycopg_async://），psycopg 只认 postgresql://
    DB_URI.replace("+psycopg_async", ""),
    max_size=10,
    # 连接池要在事件循环里打开，放到 open_checkpointer 里做
    open=False,
    # AsyncPostgresSaver 要求的连接参数，和它自带的 from_conn_string 一致
    kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
)
_checkpointer: AsyncPostgresSaver | None = None


async def open_checkpointer() -> None:
    global _checkpointer
    await pool.open()
    # AsyncPostgresSaver 创建时要拿当前的事件循环，不能在导入模块时创建
    _checkpointer = AsyncPostgresSaver(pool)
    # 建 checkpointer 自己的表，已经建过就什么都不做；这几张表不归 alembic 管
    await _checkpointer.setup()


async def close_checkpointer() -> None:
    await pool.close()


def get_checkpointer() -> AsyncPostgresSaver:
    if _checkpointer is None:
        raise RuntimeError("checkpointer 还没打开，进程启动时要先调用 open_checkpointer")
    return _checkpointer
