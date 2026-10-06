import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from agents.article import analyze_article
from core.cache import set_task_info
from models import AsyncSessionFactory
from models.article import Article, ArticleTag
from schemas.task_schema import TaskInfoSchema

logger = logging.getLogger(__name__)


async def analyze_article_task(article_id: int, task_id: str):
    try:
        # 1. 读文章和已有标签。后台任务在响应发出后才执行，接口的 session 可能已经关了，所以自己开一个
        async with AsyncSessionFactory() as session:
            async with session.begin():
                article = await session.get(Article, article_id)
                if article is None:
                    raise ValueError(f"文章 {article_id} 不存在")
                title, content = article.title, article.content
                existing_names = (await session.scalars(select(ArticleTag.name))).all()

        # 2. 调大模型。要等好几秒，放在事务外面，不然这段时间一直占着数据库连接
        analysis = await analyze_article(title, content, list(existing_names))

        # 3. 写回数据库
        async with AsyncSessionFactory() as session:
            async with session.begin():
                article = await session.get(Article, article_id, options=[selectinload(Article.tags)])
                if article is None:
                    raise ValueError(f"文章 {article_id} 在分析期间被删除了")

                article.summary = analysis.summary
                article.recommend_score = analysis.recommend_score

                # 小写做 key，AI 给的 python 能对上库里已有的 Python
                tag_by_name = {
                    tag.name.lower(): tag for tag in await session.scalars(select(ArticleTag))
                }
                applied: list[str] = []
                for name in analysis.tags:
                    key = name.lower()
                    # 没有就新建，并放进字典，避免 Redis 和 redis 各建一个
                    if key not in tag_by_name:
                        tag_by_name[key] = ArticleTag(name=name)
                    tag = tag_by_name[key]

                    # 追加，作者在分析期间手动加的标签留着
                    if tag not in article.tags:
                        article.tags.append(tag)
                    if tag.name not in applied:
                        applied.append(tag.name)
                # 返回库里实际的名字，比如 python 对应已有的 Python
                analysis.tags = applied

        await set_task_info(TaskInfoSchema(task_id=task_id, status="done", result=analysis))
    except Exception as e:
        logger.exception("文章 %s AI 分析失败", article_id)
        await set_task_info(TaskInfoSchema(task_id=task_id, status="failed", error=str(e)))
