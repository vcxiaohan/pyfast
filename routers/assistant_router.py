from collections.abc import AsyncIterable
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.sse import EventSourceResponse, ServerSentEvent

from agents.assistant import stream_assistant
from dependencies import bearer_scheme, get_current_user
from models.user import User
from routers.chat_router import disable_proxy_compression
from schemas.chat_schema import AssistantStreamSchema, ChatChunkSchema

router = APIRouter(prefix="/assistant", tags=["assistant"])


# get_current_user 在开始推流之前校验 token，过期时直接返回 401，前端据此重新登录；
# 推流开始后状态码已经是 200，再出错只能通过消息告诉前端
@router.post(
    "/stream",
    response_class=EventSourceResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(disable_proxy_compression)],
)
async def assistant_stream(
        payload: AssistantStreamSchema,
        user: User = Depends(get_current_user),
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AsyncIterable[ChatChunkSchema | ServerSentEvent]:
    # 会话和用户绑定，拿到别人的 chat_id 也接不上别人的对话
    thread_id = f"{user.id}:{payload.chat_id}"
    message_id = str(uuid4())
    try:
        async for item in stream_assistant(payload.content, thread_id, credentials.credentials):
            if isinstance(item, dict):
                yield ChatChunkSchema(message_id=message_id, card=item)
            else:
                yield ChatChunkSchema(message_id=message_id, data=item)
    except Exception as e:
        yield ChatChunkSchema(message_id=message_id, error=str(e))
    yield ServerSentEvent(raw_data="[DONE]")
