from fastapi import FastAPI

from routers.article_router import router as article_router
from routers.article_tag_router import router as article_tag_router
from routers.user_router import router as user_router

app = FastAPI()

app.include_router(user_router)
app.include_router(article_router)
app.include_router(article_tag_router)
