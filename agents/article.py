from langchain.agents import create_agent

from schemas.article_schema import ArticleAnalysisSchema

from .llms import qwen_llm
from .prompts import ANALYZE_ARTICLE_SYSTEM_PROMPT, ANALYZE_ARTICLE_USER_PROMPT

# response_format：让 agent 按 ArticleAnalysisSchema 的格式返回结构化结果
analysis_agent = create_agent(
    model=qwen_llm,
    system_prompt=ANALYZE_ARTICLE_SYSTEM_PROMPT,
    response_format=ArticleAnalysisSchema,
)

# 文章太长会多花 token，分析看前面一部分就够了
MAX_CONTENT_LENGTH = 4000


async def analyze_article(title: str, content: str, existing_tags: list[str]) -> ArticleAnalysisSchema:
    user_msg = ANALYZE_ARTICLE_USER_PROMPT.format(
        existing_tags="、".join(existing_tags) or "（暂无）",
        title=title,
        content=content[:MAX_CONTENT_LENGTH],
    )
    response = await analysis_agent.ainvoke({"messages": [{"role": "user", "content": user_msg}]})
    result: ArticleAnalysisSchema = response["structured_response"]

    # 大模型的输出不一定守规矩，这里兜底
    # 标签：去空格、去重、截断到数据库字段长度、最多 5 个
    names: list[str] = []
    for name in result.tags:
        name = name.strip()[:50]
        if name and name not in names:
            names.append(name)
    result.tags = names[:5]
    result.summary = result.summary.strip()
    # 推荐值：超出范围就拉回 1~10
    result.recommend_score = max(1, min(10, result.recommend_score))
    return result
