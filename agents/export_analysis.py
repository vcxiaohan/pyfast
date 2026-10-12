"""worker 生成完导出文件后调用：写数据解读，并追加到发起导出的那段对话里，运营接着追问时助手能接上。"""

import json

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from .checkpointer import get_checkpointer
from .llms import qwen_llm
from .prompts import EXPORT_ANALYSIS_PROMPT, EXPORT_ANALYSIS_USER_PROMPT

# 只带最近几条对话：够判断运营关注什么，又不会把 prompt 撑太长
HISTORY_LIMIT = 10
EMPTY_ANALYSIS = "这段时间没有符合条件的订单，可以换个时间范围或去掉筛选条件再试试。"


async def analyze_export(thread_id: str | None, date_range: str, row_count: int, summary: dict | None) -> str:
    # 和数据助手同一个 checkpointer、同样以 messages 为状态，只是用来读写对话记忆，不需要工具
    agent = create_agent(model=qwen_llm, tools=[], checkpointer=get_checkpointer())
    config = {"configurable": {"thread_id": thread_id}}

    history: list = []
    if thread_id:
        state = await agent.aget_state(config)
        # 工具调用和工具结果又长又和这次无关，只留运营和助手说的话
        history = [
            m for m in state.values.get("messages", [])
            if m.type in ("human", "ai") and isinstance(m.content, str) and m.content
        ][-HISTORY_LIMIT:]

    if summary is None:
        analysis = EMPTY_ANALYSIS
    else:
        lines = [f"{'运营' if m.type == 'human' else '助手'}：{m.content}" for m in history]
        reply = await qwen_llm.ainvoke([
            SystemMessage(EXPORT_ANALYSIS_PROMPT),
            HumanMessage(EXPORT_ANALYSIS_USER_PROMPT.format(
                history="\n".join(lines) or "（无）",
                date_range=date_range,
                row_count=row_count,
                summary=json.dumps(summary, ensure_ascii=False),
            )),
        ])
        analysis = reply.content.strip()

    # as_node="model"：当作模型说的一句话追加进去。运营这时正好在发新消息的话，两边同时写同一段对话可能会乱序，概率很低先不处理
    if thread_id:
        await agent.aupdate_state(config, {"messages": [AIMessage(analysis)]}, as_node="model")
    return analysis
