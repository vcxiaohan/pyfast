from collections.abc import AsyncIterator

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from .llms import qwen_llm
from .prompts import REVIEW_SYSTEM_PROMPT

# checkpointer 按 thread_id 保存每个会话的消息历史，下次带同一个 thread_id 调用时会自动带上之前的对话。
# InMemorySaver 存在进程内存里：服务重启（包括 --reload）就没了，多进程之间也不共享
review_agent = create_agent(
    model=qwen_llm,
    system_prompt=REVIEW_SYSTEM_PROMPT,
    checkpointer=InMemorySaver(),
)


async def stream_review(content: str, chat_id: str) -> AsyncIterator[str]:
    async for chunk, metadata in review_agent.astream(
            {"messages": [{"role": "user", "content": content}]},
            {"configurable": {"thread_id": chat_id}},
            stream_mode="messages",
    ):
        if metadata["langgraph_node"] == "model" and chunk.content:
            yield chunk.content
