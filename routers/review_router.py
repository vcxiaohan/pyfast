from collections.abc import AsyncIterable
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent

from agents.review import stream_review
from routers.chat_router import disable_proxy_compression
from schemas.chat_schema import ChatChunkSchema, ReviewStreamSchema

router = APIRouter(prefix="/review", tags=["review"])


# 协议和 /chat/stream 一样，区别在模型输出的内容：[END] 之前是回复文字，之后每行一条 json:{...} 评价
@router.post(
    "/stream",
    response_class=EventSourceResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(disable_proxy_compression)],
)
async def review_stream(payload: ReviewStreamSchema) -> AsyncIterable[ChatChunkSchema | ServerSentEvent]:
    # 有登录后要和用户绑定，例如 f"{user_id}:{chat_id}"，否则拿到别人的 chat_id 就能接着别人的对话
    chat_id = str(payload.chat_id)
    message_id = str(uuid4())
    try:
        async for text in stream_review(payload.content, chat_id):
            yield ChatChunkSchema(message_id=message_id, data=text)
    except Exception as e:
        yield ChatChunkSchema(message_id=message_id, error=str(e))
    yield ServerSentEvent(raw_data="[DONE]")
