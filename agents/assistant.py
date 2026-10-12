from collections.abc import AsyncIterator
from datetime import datetime
from zoneinfo import ZoneInfo

from fastmcp import Client
from langchain.agents import create_agent
from langchain.mcp import MCPAdapter

from settings import settings

from .checkpointer import get_checkpointer
from .llms import qwen_llm
from .prompts import ASSISTANT_SYSTEM_PROMPT


async def stream_assistant(content: str, thread_id: str, token: str) -> AsyncIterator[str | dict]:
    """产出两种东西：str 是模型的回复文字，dict 是要在前端渲染的卡片。"""
    # 中台助手也作为 MCP 客户端，带着用户自己的 token 连 /ai/mcp，和 Cursor 走同一套鉴权。
    # 工具列表随用户 token 变化，所以每次请求都重新加载、重新建 agent
    client = Client(settings.MCP_INTERNAL_URL, auth=token)
    tools = await MCPAdapter(client).list_tools()
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    agent = create_agent(
        model=qwen_llm,
        tools=tools,
        system_prompt=ASSISTANT_SYSTEM_PROMPT.format(today=today),
        checkpointer=get_checkpointer(),
    )

    # 模型在调工具前后各说一段话。中间有卡片时前端会自动分段，没有卡片时补一个换行，不然两段话会粘在一起
    has_text = False
    need_break = False
    async for chunk, metadata in agent.astream(
            {"messages": [{"role": "user", "content": content}]},
            {"configurable": {"thread_id": thread_id}},
            stream_mode="messages",
    ):
        node = metadata["langgraph_node"]
        if node == "model" and chunk.content:
            if need_break:
                yield "\n"
                need_break = False
            has_text = True
            yield chunk.content
        elif node == "tools":
            # 工具返回的结构化结果在 artifact 里；导出成功时推一张下载卡片，链接不靠模型转述
            result = chunk.artifact["structured_content"] if chunk.artifact else {}
            if chunk.name == "export_orders" and result.get("download_url"):
                # summary 是给模型做解读的，卡片用不到
                yield {"type": "export", **{k: v for k, v in result.items() if k != "summary"}}
            elif has_text:
                need_break = True
