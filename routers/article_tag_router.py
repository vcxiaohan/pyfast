from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from dependencies import get_admin_user, get_session
from models import AsyncSession
from models.article import ArticleAndTag, ArticleTag
from models.user import User
from schemas.article_schema import ArticleTagWithCountSchema

router = APIRouter(prefix="/article_tag", tags=["article_tag"])


@router.get("/list", response_model=list[ArticleTagWithCountSchema])
async def get_article_tag_list(session: AsyncSession = Depends(get_session)):
    async with session.begin():
        # LEFT JOIN 中间表再分组计数，没有文章的标签也会出现，数量为 0
        stmt = (
            select(
                ArticleTag.id,
                ArticleTag.name,
                func.count(ArticleAndTag.article_id).label("article_count"),
            )
            .outerjoin(ArticleAndTag, ArticleAndTag.tag_id == ArticleTag.id)
            .group_by(ArticleTag.id)
            .order_by(ArticleTag.id)
        )
        result = await session.execute(stmt)
        return result.mappings().all()


@router.post("/remove")
async def remove_article_tag(
        tag_id: int,
        user: User = Depends(get_admin_user),
        session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        data = await session.get(ArticleTag, tag_id)
        if data is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")
        await session.delete(data)
    return {"msg": "删除成功"}
