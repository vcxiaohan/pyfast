from datetime import datetime

from pydantic import BaseModel, ConfigDict

from models.article import ArticleStatus
from schemas.user_schema import UserBriefSchema


class ArticleTagSchema(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class ArticleTagWithCountSchema(ArticleTagSchema):
    article_count: int


class ArticleSetTagsSchema(BaseModel):
    article_id: int
    # 传空列表表示清空这篇文章的标签
    tag_ids: list[int]


class ArticleSchema(BaseModel):
    id: int
    title: str
    content: str
    status: ArticleStatus
    view_count: int
    create_time: datetime
    author: UserBriefSchema
    tags: list[ArticleTagSchema]
    model_config = ConfigDict(from_attributes=True)
