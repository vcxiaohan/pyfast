from uuid import UUID

from pydantic import BaseModel, Field


class ChatStreamSchema(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


# chat_id 由前端生成，同一个会话每次请求都带同一个；限定为 UUID，防止乱传超长字符串
class ReviewStreamSchema(ChatStreamSchema):
    chat_id: UUID


class AssistantStreamSchema(ChatStreamSchema):
    chat_id: UUID


# 流式返回的每一条消息；data、card、error 只会有一个，其余是 None，返回时不输出
class ChatChunkSchema(BaseModel):
    message_id: str
    data: str | None = None
    # 前端按 card["type"] 找对应的组件渲染，例如导出完成的下载卡片
    card: dict | None = None
    error: str | None = None
