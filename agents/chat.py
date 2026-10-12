from collections.abc import AsyncIterator

from langchain.agents import create_agent

from .llms import qwen_llm
from .prompts import CHAT_SYSTEM_PROMPT

chat_agent = create_agent(
    model=qwen_llm,
    system_prompt=CHAT_SYSTEM_PROMPT,
)


async def stream_chat(content: str) -> AsyncIterator[str]:
    # stream_mode="messages"：模型每吐出一小段就产出一次 (消息片段, 元数据)
    async for chunk, metadata in chat_agent.astream(
            {"messages": [{"role": "user", "content": content}]},
            stream_mode="messages",
    ):
        # 只要模型节点生成的文字；以后加了工具，工具的返回结果也会走这里，不能推给前端
        if metadata["langgraph_node"] == "model" and chunk.content:
            yield chunk.content
