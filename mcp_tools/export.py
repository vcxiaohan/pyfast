"""订单导出：工具只建任务、发消息，立刻返回；拉数据、写 Excel、写解读都在 worker 里做。"""

from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token, get_http_headers

from core.mq import get_channel, publish_export_task
from models import AsyncSessionFactory
from models.export_task import ExportStatus, ExportTask
from services.export_service import FIELD_LABELS, MAX_DAYS, OrderField, get_task_view
from services.order_source import OrderQuery


async def export_orders(
        start_date: date | None = None,
        end_date: date | None = None,
        # 不要写成 list | None：schema 变成 anyOf，千问会把数组当成 JSON 字符串传，校验不通过
        fields: list[OrderField] = [],
        utm_source: Literal["douyin", "kuaishou", "gdt", "natural"] | None = None,
        status: Literal["pending", "paid", "shipped", "completed", "refunded", "cancelled"] | None = None,
        shop_name: str | None = None,
) -> dict:
    """按下单时间导出订单明细 Excel。文件在后台生成，调用后立刻返回 task_id，用 get_export_status 查进度。

    - 用户没说日期时默认今天，回复里要告诉用户导出的是哪段时间；只说了一天就把 start_date 和 end_date 都设成那天。
    - fields 是用户要的列，按用户说的顺序传；没指定就导出全部。“下单人”“买家”对应 buyer_phone（已脱敏）。
    - utm_source 渠道：douyin 抖音、kuaishou 快手、gdt 广点通、natural 自然流量。
    - 一次最多 92 天、10 万行。
    """
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    start_date = start_date or end_date or today
    end_date = end_date or start_date
    if start_date > end_date:
        raise ToolError("开始日期不能晚于结束日期")
    if (end_date - start_date).days + 1 > MAX_DAYS:
        raise ToolError(f"一次最多导出 {MAX_DAYS} 天，请缩小时间范围")
    fields = list(dict.fromkeys(fields)) if fields else list(FIELD_LABELS)

    query = OrderQuery(start_date=start_date, end_date=end_date, utm_source=utm_source, status=status, shop_name=shop_name)
    task = ExportTask(
        user_id=int(get_access_token().client_id),
        # 数据助手通过请求头带上当前对话，worker 生成完会把解读写回这段对话；从 Cursor 调用时没有
        thread_id=get_http_headers().get("x-thread-id"),
        export_type="orders",
        params={"query": query.model_dump(mode="json"), "fields": fields},
    )
    # 先落库再发消息：反过来的话，worker 可能先收到消息却查不到任务
    async with AsyncSessionFactory() as session:
        session.add(task)
        await session.commit()

    try:
        await publish_export_task(get_channel(), task.id)
    except Exception as e:
        async with AsyncSessionFactory() as session:
            failed = await session.get(ExportTask, task.id)
            failed.status = ExportStatus.FAILED
            failed.error_msg = f"发送到队列失败：{e}"
            await session.commit()
        raise ToolError("导出服务暂时不可用，请稍后再试")

    return {
        "task_id": task.id,
        "status": task.status,
        "date_range": f"{start_date} ~ {end_date}",
        "columns": [FIELD_LABELS[f] for f in fields],
    }


async def get_export_status(task_id: str) -> dict:
    """查导出任务的进度和统计数据。status：pending 排队中、running 生成中、done 已完成、failed 失败。

    完成后返回下载链接、统计摘要 summary 和已经写好的数据解读 analysis。
    summary 是用这批订单全部字段的明细算的，包含渠道、商品、店铺、退款等统计，和导出了哪些列无关。
    用户追问刚导出的这批数据时调用它，用 summary 回答。
    """
    view = await get_task_view(task_id, int(get_access_token().client_id))
    if view is None:
        raise ToolError("导出任务不存在")
    return view
