from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.cache import redis_client
from routers.article_router import router as article_router
from routers.article_tag_router import router as article_tag_router
from routers.user_router import router as user_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # yield 之前是启动时执行，之后是程序退出前执行
    # 启动时试连一次 Redis，没开就直接启动失败，而不是等到调接口才报 500
    await redis_client.ping()
    yield
    await redis_client.aclose()


app = FastAPI(lifespan=lifespan)

app.include_router(user_router)
app.include_router(article_router)
app.include_router(article_tag_router)
