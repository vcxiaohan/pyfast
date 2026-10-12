from collections.abc import AsyncIterable
from uuid import uuid4

from fastapi import APIRouter, Depends, Response
from fastapi.sse import EventSourceResponse, ServerSentEvent

from agents.chat import stream_chat
from schemas.chat_schema import ChatChunkSchema, ChatStreamSchema

router = APIRouter(prefix="/chat", tags=["chat"])


# EventSourceResponse 自带 Cache-Control: no-cache，但没有 no-transform，
# 经过会做 gzip 的代理（比如 Next）时会被攒成一整块再发。
# 要放在依赖里设置：接口本身是生成器，函数体执行时响应头可能已经发出去了
def disable_proxy_compression(response: Response):
    response.headers["Cache-Control"] = "no-cache, no-transform"


# response_class=EventSourceResponse + 接口里 yield：每 yield 一个对象，就转成 JSON 发一条 "data: ...\n\n"。
# 框架还会自动设置 text/event-stream、X-Accel-Buffering: no，空闲 15 秒发一次 ": ping" 心跳
@router.post(
    "/stream",
    response_class=EventSourceResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(disable_proxy_compression)],
)
async def chat_stream(payload: ChatStreamSchema) -> AsyncIterable[ChatChunkSchema | ServerSentEvent]:
    message_id = str(uuid4())
    try:
        async for text in stream_chat(payload.content):
            yield ChatChunkSchema(message_id=message_id, data=text)
    except Exception as e:
        # 响应头（200）已经发出去了，出错只能通过消息告诉前端
        yield ChatChunkSchema(message_id=message_id, error=str(e))
    # raw_data 原样发送；用 data= 的话字符串也会被 JSON 编码，变成带引号的 "[DONE]"
    yield ServerSentEvent(raw_data="[DONE]")
