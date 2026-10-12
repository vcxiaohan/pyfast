"""RabbitMQ：导出任务队列。API 进程只发消息，worker 进程消费。

消息体只有任务 id，导出条件存在 export_task 表里：消息小，重试时也能拿到原始条件。
"""

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractQueue, AbstractRobustConnection

from settings import settings

EXPORT_QUEUE = "export.tasks"
# 死信队列：重试次数用完的消息转到这里，留着排查，不会丢
EXPORT_DEAD_QUEUE = "export.tasks.dead"

_connection: AbstractRobustConnection | None = None
_channel: AbstractChannel | None = None


async def connect() -> AbstractRobustConnection:
    # robust 连接断开后会自动重连，并恢复之前声明的队列和消费者
    return await aio_pika.connect_robust(settings.RABBITMQ_URL)


async def declare_queues(channel: AbstractChannel) -> AbstractQueue:
    """API 和 worker 启动时都声明一遍，谁先启动都行；队列已存在且参数相同时什么都不做。"""
    await channel.declare_queue(EXPORT_DEAD_QUEUE, durable=True)
    # durable：RabbitMQ 重启后队列还在。被 reject 的消息按下面的参数转进死信队列
    return await channel.declare_queue(
        EXPORT_QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": EXPORT_DEAD_QUEUE},
    )


async def publish_export_task(channel: AbstractChannel, task_id: str) -> None:
    # 持久化消息：RabbitMQ 重启后消息还在。channel 默认开了 publisher confirms，
    # 这里会等 RabbitMQ 确认收到才返回，发送失败会直接抛异常
    message = aio_pika.Message(body=task_id.encode(), message_id=task_id, delivery_mode=aio_pika.DeliveryMode.PERSISTENT)
    await channel.default_exchange.publish(message, routing_key=EXPORT_QUEUE)


async def open_mq() -> None:
    """API 进程启动时调用，整个进程共用一个连接和 channel 发消息。"""
    global _connection, _channel
    _connection = await connect()
    _channel = await _connection.channel()
    await declare_queues(_channel)


async def close_mq() -> None:
    if _connection:
        await _connection.close()


def get_channel() -> AbstractChannel:
    if _channel is None:
        raise RuntimeError("RabbitMQ 还没连接，进程启动时要先调用 open_mq")
    return _channel
