from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.cache import get_task_info, set_task_info
from dependencies import get_author_user, get_current_user, get_session
from models import AsyncSession
from models.article import Article, ArticleTag
from models.user import User
from schemas.article_schema import ArticleCreateRespSchema, ArticleCreateSchema, ArticleSchema, ArticleSetTagsSchema
from schemas.task_schema import TaskInfoSchema
from tasks.article_task import analyze_article_task

router = APIRouter(prefix="/article", tags=["article"])


@router.get("/list", response_model=list[ArticleSchema])
async def get_article_list(
        page: int = Query(1, ge=1),
        size: int = Query(10, ge=1, le=100),
        session: AsyncSession = Depends(get_session),
):
    async with session.begin():
        stmt = (
            select(Article)
            .options(selectinload(Article.author), selectinload(Article.tags))
            .order_by(Article.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        articles = await session.scalars(stmt)
        return articles.all()


@router.post("/create", response_model=ArticleCreateRespSchema, status_code=status.HTTP_201_CREATED)
async def create_article(
        payload: ArticleCreateSchema,
        background_tasks: BackgroundTasks,
        user: User = Depends(get_author_user),
        session: AsyncSession = Depends(get_session),
):
    async with session.begin():
        article = Article(**payload.model_dump(), author_id=user.id)
        session.add(article)
        await session.flush()
        # 新建对象的 author、tags 还没加载，async 下不能懒加载，手动加载出来给响应用
        await session.refresh(article, attribute_names=["author", "tags"])

    task_id = str(uuid4())
    # 先写 pending 再返回 task_id，否则前端拿到 task_id 马上来查会查不到
    await set_task_info(TaskInfoSchema(task_id=task_id, status="pending"))
    # 只是登记，响应发给前端之后才执行
    background_tasks.add_task(analyze_article_task, article.id, task_id)
    return {"article": article, "task_id": task_id}


@router.get("/analyze_task/{task_id}", response_model=TaskInfoSchema)
async def get_analyze_task(task_id: str, _: User = Depends(get_current_user)):
    task_info = await get_task_info(task_id)
    if task_info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在或已过期")
    return task_info


@router.put("/set_tags", response_model=ArticleSchema)
async def set_article_tags(payload: ArticleSetTagsSchema, session: AsyncSession = Depends(get_session)):
    async with session.begin():
        article = await session.get(
            Article,
            payload.article_id,
            options=[selectinload(Article.author), selectinload(Article.tags)],
        )
        if article is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文章不存在")

        tag_ids = set(payload.tag_ids)
        tags = (await session.scalars(select(ArticleTag).where(ArticleTag.id.in_(tag_ids)))).all()
        missing = tag_ids - {tag.id for tag in tags}
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"标签不存在：{sorted(missing)}")

        # 直接整体赋值，SQLAlchemy 会对比新旧列表，自动在中间表里删掉多余的、插入新增的
        article.tags = list(tags)
    return article
