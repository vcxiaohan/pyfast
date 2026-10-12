from contextlib import asynccontextmanager

from fastapi import FastAPI

from agents.checkpointer import close_checkpointer, open_checkpointer
from core.cache import redis_client
from core.mq import close_mq, open_mq
from mcp_server import mcp_app
from routers.article_router import router as article_router
from routers.article_tag_router import router as article_tag_router
from routers.assistant_router import router as assistant_router
from routers.chat_router import router as chat_router
from routers.export_router import router as export_router
from routers.review_router import router as review_router
from routers.user_router import router as user_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # yield 之前是启动时执行，之后是程序退出前执行
    # 启动时试连一次 Redis，没开就直接启动失败，而不是等到调接口才报 500
    await redis_client.ping()
    await open_checkpointer()
    await open_mq()
    # 挂载的子应用的 lifespan 不会被 FastAPI 执行，MCP 的会话管理器要在这里手动启动，否则调 /ai/mcp 会报错
    async with mcp_app.lifespan(app):
        yield
    await close_mq()
    await close_checkpointer()
    await redis_client.aclose()


app = FastAPI(lifespan=lifespan)


# 给 Docker 和负载均衡做健康检查。只说明进程活着、能接请求，不查数据库：
# 数据库抖一下就把所有实例判成不健康、全部摘掉，反而整个服务不可用
@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(user_router)
app.include_router(article_router)
app.include_router(article_tag_router)
app.include_router(chat_router)
app.include_router(review_router)
app.include_router(export_router)
app.include_router(assistant_router)

# MCP 地址：/ai/mcp
app.mount("/ai", mcp_app)
