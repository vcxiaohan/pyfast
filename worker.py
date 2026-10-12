"""导出 worker：消费 RabbitMQ 里的导出任务，生成 Excel 和数据解读。

独立进程，不监听端口，主动连 RabbitMQ 取消息。在 pyfast 目录下执行：python worker.py
要多处理几个任务就多开几个进程，RabbitMQ 会把消息轮流分给它们。
"""

import asyncio
import logging
import signal
from datetime import datetime

from aio_pika.abc import AbstractChannel, AbstractIncomingMessage

from agents.checkpointer import close_checkpointer, open_checkpointer
from agents.export_analysis import analyze_export
from core.cache import redis_client, set_export_progress
from core.mq import connect, declare_queues, publish_export_task
from models import AsyncSessionFactory
from models.export_task import ExportStatus, ExportTask
from services.export_service import ExportError, generate_order_export

logger = logging.getLogger("worker")

MAX_RETRIES = 3


async def process(task_id: str) -> None:
    async with AsyncSessionFactory() as session:
        task = await session.get(ExportTask, task_id)
        if task is None:
            logger.warning("任务 %s 不存在，丢弃消息", task_id)
            return
        # 幂等：同一条消息可能被投递多次（例如处理完还没来得及 ack 进程就挂了），已经结束的任务不再重复生成。
        # running 的不跳过：说明上一个 worker 处理到一半挂了，消息被重新投递，要接着做
        if task.status in (ExportStatus.DONE, ExportStatus.FAILED):
            logger.info("任务 %s 已经是 %s，跳过", task_id, task.status)
            return
        task.status = ExportStatus.RUNNING
        await session.commit()
        params, thread_id = task.params, task.thread_id

    output = await generate_order_export(task_id, params)
    result = output["result"]
    await set_export_progress(task_id, 95, "AI 正在分析数据")
    try:
        analysis = await analyze_export(thread_id, result["date_range"], output["row_count"], result["summary"])
    except Exception:
        # 解读只是锦上添花，失败了文件照样能下载
        logger.exception("任务 %s 写解读失败", task_id)
        analysis = None

    # 文件和解读都好了再标记完成，卡片轮询到 done 时两样一起显示
    async with AsyncSessionFactory() as session:
        task = await session.get(ExportTask, task_id)
        task.status = ExportStatus.DONE
        task.file_key = output["file_key"]
        task.file_name = output["file_name"]
        task.row_count = output["row_count"]
        task.result = {**result, "analysis": analysis}
        task.error_msg = None
        task.finished_at = datetime.now()
        await session.commit()
    logger.info("任务 %s 完成，%s 行", task_id, output["row_count"])


async def record_failure(task_id: str, error: str, retryable: bool) -> bool:
    """记下失败原因。还能重试时把状态改回 pending 并返回 True；不能重试时标记失败，返回 False。"""
    async with AsyncSessionFactory() as session:
        task = await session.get(ExportTask, task_id)
        if task is None:
            return False
        task.error_msg = error
        if retryable and task.retry_count < MAX_RETRIES:
            task.retry_count += 1
            task.status = ExportStatus.PENDING
            await session.commit()
            return True
        task.status = ExportStatus.FAILED
        task.finished_at = datetime.now()
        await session.commit()
        return False


async def handle(message: AbstractIncomingMessage, channel: AbstractChannel) -> None:
    task_id = message.body.decode()
    try:
        await process(task_id)
    except ExportError as e:
        # 数据本身的问题（例如超过行数上限），重试也一样，直接失败，消息确认掉
        await record_failure(task_id, str(e), retryable=False)
        await message.ack()
        return
    except Exception as e:
        logger.exception("任务 %s 失败", task_id)
        if await record_failure(task_id, str(e), retryable=True):
            # 重新发一条排到队尾，再确认旧消息。顺序反过来的话，中间进程挂了这个任务就丢了；
            # 现在这样最坏是消息重复，process 里的状态判断会跳过
            await publish_export_task(channel, task_id)
            await message.ack()
        else:
            # reject 且不重新入队：消息按队列参数转进死信队列，留着排查
            await message.reject(requeue=False)
        return
    await message.ack()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # docker stop 和发布时先发 SIGTERM：不再接新任务，手上这个做完再退出。
    # 直接退出也不会丢任务（没 ack 的消息会重新投递），只是做了一半的要从头再来
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    await open_checkpointer()
    connection = await connect()
    try:
        channel = await connection.channel()
        # 一次只取一条：导出要跑很久，多取的消息只能在这里干等，不如留给别的 worker
        await channel.set_qos(prefetch_count=1)
        queue = await declare_queues(channel)

        busy = asyncio.Lock()

        async def on_message(message: AbstractIncomingMessage) -> None:
            async with busy:
                await handle(message, channel)

        consumer_tag = await queue.consume(on_message)
        logger.info("worker 已启动，等待导出任务")
        await stop.wait()

        logger.info("收到退出信号，不再接新任务，等手上的任务做完")
        await queue.cancel(consumer_tag)
        async with busy:
            pass
    finally:
        await connection.close()
        await close_checkpointer()
        await redis_client.aclose()
    logger.info("worker 已退出")


if __name__ == "__main__":
    asyncio.run(main())
