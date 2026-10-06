from typing import Literal

from pydantic import BaseModel

from schemas.article_schema import ArticleAnalysisSchema


class TaskInfoSchema(BaseModel):
    task_id: str
    status: Literal["pending", "done", "failed"]
    # done 时是 AI 分析的结果（标签、摘要、推荐值）
    result: ArticleAnalysisSchema | None = None
    # failed 时是错误信息
    error: str | None = None
