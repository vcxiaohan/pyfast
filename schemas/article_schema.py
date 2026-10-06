from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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
    # AI 分析完成前是 null
    summary: str | None
    recommend_score: int | None
    create_time: datetime
    author: UserBriefSchema
    tags: list[ArticleTagSchema]
    model_config = ConfigDict(from_attributes=True)


class ArticleCreateSchema(BaseModel):
    # examples 只用来在 /docs 里预填示例，不是默认值，字段仍然必填
    title: str = Field(min_length=1, max_length=100, examples=["PostgreSQL 索引入门：什么时候该加索引"])
    content: str = Field(
        min_length=1,
        examples=[
            "随着数据量变大，很多查询会越来越慢，这时候第一个要想到的就是索引。"
            "索引就像书的目录，能让数据库不用逐行扫描整张表就找到目标数据。"
            "一般来说，经常出现在 WHERE、JOIN、ORDER BY 里的字段适合加索引；"
            "但索引也不是越多越好，每次插入和更新都要同步维护索引，写入会变慢。"
            "本文用几个实际例子，演示如何用 EXPLAIN 查看执行计划，判断一个索引到底有没有生效。"
        ],
    )
    status: ArticleStatus = ArticleStatus.DRAFT


class ArticleCreateRespSchema(BaseModel):
    article: ArticleSchema
    # 拿它去 GET /article/analyze_task/{task_id} 查 AI 分析的进度
    task_id: str


# 大模型的结构化输出：description 会作为字段说明发给大模型
# min_length / max_length / ge / le 是硬约束，大模型的输出不满足会校验报错，任务变成 failed
class ArticleAnalysisSchema(BaseModel):
    tags: list[str] = Field(min_length=1, max_length=5, description="1~5 个标签名，优先使用已有标签的原名")
    # 摘要不加长度限制：多写几个字就让整个任务失败不划算，长度靠提示词约束
    summary: str = Field(description="文章摘要，100 字以内")
    recommend_score: int = Field(ge=1, le=10, description="推荐值，1~10 的整数，越高越值得推荐")
