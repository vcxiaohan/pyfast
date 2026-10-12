"""异步导出任务：工具建任务、发消息，worker 消费后生成文件，前端和模型都按 id 查进度。"""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class ExportStatus(StrEnum):
    PENDING = "pending"  # 已入队，等 worker 处理
    RUNNING = "running"  # worker 正在生成
    DONE = "done"
    FAILED = "failed"  # 重试次数用完仍失败


class ExportTask(Base):
    __tablename__ = "export_task"
    # 查“我的导出记录”按用户、时间倒序
    __table_args__ = (Index("ix_export_task_user_id_create_time", "user_id", "create_time"),)
    # id 会出现在前端轮询的 URL 里，用随机串，不暴露任务总量，也没法挨个猜别人的任务
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"))
    # 从数据助手发起时才有；worker 用它读对话上下文写解读，再把解读追加回这段对话。从 Cursor 调用时为空
    thread_id: Mapped[str | None] = mapped_column(String(100), comment="发起导出的对话")
    export_type: Mapped[str] = mapped_column(String(32), comment="导出类型，例如 orders")
    params: Mapped[dict] = mapped_column(JSONB, comment="导出条件，worker 按这个重新查数据")
    status: Mapped[str] = mapped_column(String(20), default=ExportStatus.PENDING, comment="状态")
    file_key: Mapped[str | None] = mapped_column(String(255), comment="文件在存储里的路径，上 OSS 后就是对象 key")
    file_name: Mapped[str | None] = mapped_column(String(255), comment="下载时的文件名")
    row_count: Mapped[int | None] = mapped_column(Integer, comment="导出行数")
    result: Mapped[dict | None] = mapped_column(JSONB, comment="时间范围、列名、统计摘要，给卡片和模型用")
    error_msg: Mapped[str | None] = mapped_column(Text, comment="失败原因")
    retry_count: Mapped[int] = mapped_column(Integer, default=0, comment="已重试次数")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, comment="完成或最终失败的时间")
