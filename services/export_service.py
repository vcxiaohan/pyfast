"""订单导出：worker 用它拉明细、算统计摘要、写 Excel；工具和查询接口用它拼任务进度。"""

import asyncio
import io
import math
from datetime import timedelta
from typing import Literal
from uuid import uuid4

import pandas as pd

from core.cache import get_export_progress, set_export_progress
from core.oss import sign_download_url, upload
from models import AsyncSessionFactory
from models.export_task import ExportStatus, ExportTask
from services.order_source import OrderQuery, list_orders
from settings import settings

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOWNLOAD_EXPIRES = timedelta(minutes=10)
MAX_DAYS = 92
MAX_ROWS = 100_000
PAGE_SIZE = 1000

OrderField = Literal[
    "order_no", "shop_name", "product_name", "quantity", "amount",
    "status", "utm_source", "buyer_phone", "create_time", "paid_time",
]

# 允许导出的字段和中文表头。模型只能从这里选，不能自己指定列名
FIELD_LABELS: dict[OrderField, str] = {
    "order_no": "订单号",
    "shop_name": "店铺",
    "product_name": "商品",
    "quantity": "数量",
    "amount": "实付金额（元）",
    "status": "订单状态",
    "utm_source": "来源渠道",
    "buyer_phone": "下单人手机号",
    "create_time": "下单时间",
    "paid_time": "支付时间",
}

STATUS_LABELS = {
    "pending": "待支付", "paid": "已支付", "shipped": "已发货",
    "completed": "已完成", "refunded": "已退款", "cancelled": "已取消",
}
CHANNEL_LABELS = {"douyin": "抖音", "kuaishou": "快手", "gdt": "广点通", "natural": "自然流量"}
DEAL_STATUSES = ["paid", "shipped", "completed"]


class ExportError(Exception):
    """数据本身导致的失败，例如超过行数上限。重试也没用，worker 直接标记失败。"""


def group_deals(df: pd.DataFrame, column: str, labels: dict[str, str] | None = None) -> list[dict]:
    """按某一列统计单数和金额，金额从高到低排。"""
    grouped = df.groupby(column)["amount"].agg(["count", "sum"]).sort_values("sum", ascending=False)
    return [
        {"name": labels.get(key, key) if labels else key, "count": int(row["count"]), "amount": round(float(row["sum"]) / 100, 2)}
        for key, row in grouped.iterrows()
    ]


def build_summary(df: pd.DataFrame) -> dict:
    """给模型做数据解读的统计数字。用拉到的全部明细算，和用户选了哪些列无关；只给汇总不给明细，手机号这类字段不会经过模型。"""
    deals = df[df["status"].isin(DEAL_STATUSES)]
    refunds = df[df["status"] == "refunded"]
    deal_amount = float(deals["amount"].sum()) / 100
    # 退款单也是付过款的，退款率 = 退款单 / (成交单 + 退款单)
    paid_count = len(deals) + len(refunds)
    summary = {
        "order_count": len(df),
        "deal_count": len(deals),
        "deal_amount": round(deal_amount, 2),
        "avg_order_amount": round(deal_amount / len(deals), 2) if len(deals) else 0,
        "refund_count": len(refunds),
        "refund_rate": f"{len(refunds) / paid_count:.1%}" if paid_count else "0.0%",
        "status_counts": {STATUS_LABELS.get(k, k): int(v) for k, v in df["status"].value_counts().items()},
        "by_channel": group_deals(deals, "utm_source", CHANNEL_LABELS),
        "top_products": group_deals(deals, "product_name")[:5],
        "refund_products": group_deals(refunds, "product_name")[:3],
        "refund_by_channel": group_deals(refunds, "utm_source", CHANNEL_LABELS),
    }
    if df["shop_name"].nunique() > 1:
        summary["by_shop"] = group_deals(deals, "shop_name")
    return summary


def to_xlsx(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    return buffer.getvalue()


async def generate_order_export(task_id: str, params: dict) -> dict:
    """按任务里存的条件分页拉订单、算统计摘要、写 Excel。返回要写回任务表的字段。

    进度分配：拉数据 0~70%（按已拉行数算），生成 Excel 75%，上传 90%，worker 写解读 95%。
    """
    query = OrderQuery(**params["query"])
    fields: list[OrderField] = params["fields"]

    await set_export_progress(task_id, 0, "正在拉取数据")
    rows: list[dict] = []
    page = 1
    while True:
        items, total = await list_orders(query, page, PAGE_SIZE)
        if total > MAX_ROWS:
            raise ExportError(f"共 {total} 行，超过 {MAX_ROWS} 行的上限，请缩小时间范围或增加筛选条件")
        rows.extend(items)
        # 第一页就能拿到总行数，之后每拉完一页都知道完成了几成
        if total:
            await set_export_progress(task_id, len(rows) * 70 // total, f"正在拉取数据 {len(rows):,} / {total:,} 行")
        if settings.EXPORT_DEMO_DELAY:
            await asyncio.sleep(settings.EXPORT_DEMO_DELAY / max(1, math.ceil(total / PAGE_SIZE)))
        if page * PAGE_SIZE >= total:
            break
        page += 1

    result = {"date_range": f"{query.start_date} ~ {query.end_date}", "columns": [FIELD_LABELS[f] for f in fields]}
    if not rows:
        return {"file_key": None, "file_name": None, "row_count": 0, "result": {**result, "summary": None}}

    full = pd.DataFrame(rows)
    summary = build_summary(full)

    df = full[fields].copy()
    if "amount" in df:
        df["amount"] = df["amount"] / 100
    if "buyer_phone" in df:
        df["buyer_phone"] = df["buyer_phone"].str[:3] + "****" + df["buyer_phone"].str[-4:]
    if "status" in df:
        df["status"] = df["status"].map(STATUS_LABELS)
    if "utm_source" in df:
        df["utm_source"] = df["utm_source"].map(CHANNEL_LABELS)
    df = df.rename(columns=FIELD_LABELS)

    # 写 Excel 是阻塞操作，放到线程里执行，不卡住事件循环；在内存里生成，不落本地磁盘
    await set_export_progress(task_id, 75, "正在生成 Excel")
    data = await asyncio.to_thread(to_xlsx, df)
    file_key = f"exports/{uuid4().hex}.xlsx"
    await set_export_progress(task_id, 90, "正在上传文件")
    await upload(file_key, data, XLSX_TYPE)

    return {
        "file_key": file_key,
        "file_name": f"订单明细_{query.start_date:%Y%m%d}-{query.end_date:%Y%m%d}.xlsx",
        "row_count": len(df),
        "result": {**result, "summary": summary},
    }


async def get_task_view(task_id: str, user_id: int) -> dict | None:
    """任务进度，给前端卡片轮询和 get_export_status 工具用。只能查自己的任务，查别人的和不存在一样返回 None。"""
    async with AsyncSessionFactory() as session:
        task = await session.get(ExportTask, task_id)
    if task is None or task.user_id != user_id:
        return None

    result = task.result or {}
    view = {
        "task_id": task.id,
        "status": task.status,
        "date_range": result.get("date_range") or f"{task.params['query']['start_date']} ~ {task.params['query']['end_date']}",
        "columns": result.get("columns") or [FIELD_LABELS[f] for f in task.params["fields"]],
        "row_count": task.row_count,
        "analysis": result.get("analysis"),
        "summary": result.get("summary"),
        "error": task.error_msg if task.status == ExportStatus.FAILED else None,
    }
    if task.status == ExportStatus.RUNNING:
        view["progress"] = await get_export_progress(task.id)
    # 下载链接每次查询时现签，10 分钟过期后再查一次就能拿到新链接；浏览器拿着链接直接从 OSS 下载
    if task.status == ExportStatus.DONE and task.file_key:
        view["download_url"] = sign_download_url(task.file_key, task.file_name, DOWNLOAD_EXPIRES)
        view["expires_in_minutes"] = int(DOWNLOAD_EXPIRES.total_seconds() // 60)
    return view
