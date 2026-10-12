from langchain_openai import ChatOpenAI

from settings import settings

# 千问提供 OpenAI 兼容接口，所以用 ChatOpenAI 换个 base_url 就能调
qwen_llm = ChatOpenAI(
    model="qwen3.8-max",
    base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
    api_key=settings.DASHSCOPE_API_KEY,
    # qwen3.8 默认先思考再回答，思考内容不在 content 里，前端要干等好几秒才出字
    extra_body={"enable_thinking": False},
)
