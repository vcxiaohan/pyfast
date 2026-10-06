from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from dependencies import get_session
from models import AsyncSession
from models.article import Article, ArticleTag
from schemas.article_schema import ArticleSchema, ArticleSetTagsSchema

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
