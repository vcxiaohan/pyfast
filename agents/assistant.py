from collections.abc import AsyncIterator
from datetime import datetime
from zoneinfo import ZoneInfo

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
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
    # X-Thread-Id 告诉导出工具是哪段对话发起的，worker 生成完把解读写回这段对话
    transport = StreamableHttpTransport(settings.MCP_INTERNAL_URL, headers={"X-Thread-Id": thread_id}, auth=token)
    client = Client(transport)
    tools = await MCPAdapter(client).list_tools()
    for tool in tools:
        # 导出建好任务后直接结束这一轮，模型不再接话：生成进度和解读都显示在卡片里，再说一句只会排在解读后面
        if tool.name == "export_orders":
            tool.return_direct = True
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
    last_text = ""
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
            last_text = chunk.content
            yield chunk.content
        elif node == "tools":
            # 工具返回的结构化结果在 artifact 里；导出任务建好就推一张卡片，卡片自己轮询进度
            result = chunk.artifact["structured_content"] if chunk.artifact else {}
            if chunk.name == "export_orders" and result.get("task_id"):
                yield {"type": "export", **result}
            elif chunk.name == "export_orders" and chunk.status == "error":
                # return_direct 报错时也直接结束，模型没机会解释，把工具给的原因直接告诉用户
                yield ("" if last_text.endswith("\n") else "\n") + f"导出没成功：{chunk.text}"
            elif has_text:
                need_break = True
