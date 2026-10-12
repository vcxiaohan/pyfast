"""订单导出：按对话里提到的条件和字段，生成只包含这些列的 Excel。"""

import asyncio
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
from fastmcp.exceptions import ToolError
from sqlalchemy import select

from core.auth import create_download_token
from models import AsyncSessionFactory
from models.mall import MallOrder, Product, Shop
from settings import settings

EXPORT_DIR = Path(__file__).resolve().parent.parent / "exports"
DOWNLOAD_EXPIRES = timedelta(minutes=10)
MAX_DAYS = 92
MAX_ROWS = 100_000

OrderField = Literal[
    "order_no", "shop_name", "product_name", "quantity", "amount",
    "status", "utm_source", "buyer_phone", "create_time", "paid_time",
]

# 允许导出的字段：字段名 -> (中文表头, 查询的列)。模型只能从这里选，不能自己指定列名
ORDER_FIELDS: dict[OrderField, tuple[str, object]] = {
    "order_no": ("订单号", MallOrder.order_no),
    "shop_name": ("店铺", Shop.name),
    "product_name": ("商品", Product.name),
    "quantity": ("数量", MallOrder.quantity),
    "amount": ("实付金额（元）", MallOrder.amount),
    "status": ("订单状态", MallOrder.status),
    "utm_source": ("来源渠道", MallOrder.utm_source),
    "buyer_phone": ("下单人手机号", MallOrder.buyer_phone),
    "create_time": ("下单时间", MallOrder.create_time),
    "paid_time": ("支付时间", MallOrder.paid_time),
}

STATUS_LABELS = {
    "pending": "待支付", "paid": "已支付", "shipped": "已发货",
    "completed": "已完成", "refunded": "已退款", "cancelled": "已取消",
}
CHANNEL_LABELS = {"douyin": "抖音", "kuaishou": "快手", "gdt": "广点通", "natural": "自然流量"}

# 统计摘要要用到的列：用户没选也要查出来，只是不写进 Excel
SUMMARY_FIELDS: list[OrderField] = ["shop_name", "product_name", "amount", "status", "utm_source"]
DEAL_STATUSES = ["paid", "shipped", "completed"]


def group_deals(df: pd.DataFrame, column: str, labels: dict[str, str] | None = None) -> list[dict]:
    """按某一列统计单数和金额，金额从高到低排。"""
    grouped = df.groupby(column)["amount"].agg(["count", "sum"]).sort_values("sum", ascending=False)
    return [
        {"name": labels.get(key, key) if labels else key, "count": int(row["count"]), "amount": round(float(row["sum"]) / 100, 2)}
        for key, row in grouped.iterrows()
    ]


def build_summary(df: pd.DataFrame) -> dict:
    """给模型做数据解读的统计数字。只给汇总不给明细：省 token，手机号这类字段也不会经过模型。"""
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
    }
    if df["shop_name"].nunique() > 1:
        summary["by_shop"] = group_deals(deals, "shop_name")
    return summary


async def export_orders(
        start_date: date | None = None,
        end_date: date | None = None,
        # 不要写成 list | None：schema 变成 anyOf，千问会把数组当成 JSON 字符串传，校验不通过
        fields: list[OrderField] = [],
        utm_source: Literal["douyin", "kuaishou", "gdt", "natural"] | None = None,
        status: Literal["pending", "paid", "shipped", "completed", "refunded", "cancelled"] | None = None,
        shop_name: str | None = None,
) -> dict:
    """按下单时间导出订单明细 Excel，返回下载链接（10 分钟内有效）。

    - 用户没说日期时默认今天，回复里要告诉用户导出的是哪段时间；只说了一天就把 start_date 和 end_date 都设成那天。
    - fields 是用户要的列，按用户说的顺序传；没指定就导出全部。“下单人”“买家”对应 buyer_phone（已脱敏）。
    - utm_source 渠道：douyin 抖音、kuaishou 快手、gdt 广点通、natural 自然流量。
    - 一次最多 92 天、10 万行。
    - 返回的 summary 是这批订单的统计数字（不受 fields 影响），用来给运营做数据解读。
    """
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    start_date = start_date or end_date or today
    end_date = end_date or start_date
    if start_date > end_date:
        raise ToolError("开始日期不能晚于结束日期")
    if (end_date - start_date).days + 1 > MAX_DAYS:
        raise ToolError(f"一次最多导出 {MAX_DAYS} 天，请缩小时间范围")
    fields = list(dict.fromkeys(fields)) if fields else list(ORDER_FIELDS)
    query_fields = list(dict.fromkeys(fields + SUMMARY_FIELDS))

    stmt = (
        select(*[ORDER_FIELDS[f][1] for f in query_fields])
        .select_from(MallOrder)
        .join(Product, Product.id == MallOrder.product_id)
        .join(Shop, Shop.id == MallOrder.shop_id)
        .where(
            MallOrder.create_time >= datetime.combine(start_date, time.min),
            MallOrder.create_time < datetime.combine(end_date + timedelta(days=1), time.min),
        )
        .order_by(MallOrder.create_time)
        # 多查一行，用来判断有没有超过上限
        .limit(MAX_ROWS + 1)
    )
    if utm_source:
        stmt = stmt.where(MallOrder.utm_source == utm_source)
    if status:
        stmt = stmt.where(MallOrder.status == status)
    if shop_name:
        stmt = stmt.where(Shop.name.contains(shop_name))

    async with AsyncSessionFactory() as session:
        rows = (await session.execute(stmt)).all()

    date_range = f"{start_date} ~ {end_date}"
    if not rows:
        return {"row_count": 0, "date_range": date_range, "message": "没有符合条件的订单，未生成文件"}
    if len(rows) > MAX_ROWS:
        raise ToolError(f"超过 {MAX_ROWS} 行，请缩小时间范围或增加筛选条件")

    full = pd.DataFrame(rows, columns=query_fields)
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
    df = df.rename(columns={f: ORDER_FIELDS[f][0] for f in fields})

    EXPORT_DIR.mkdir(exist_ok=True)
    file = f"{uuid4().hex}.xlsx"
    # 写 Excel 是阻塞操作，放到线程里执行，不卡住同一进程里的其他请求
    await asyncio.to_thread(df.to_excel, EXPORT_DIR / file, index=False)

    name = f"订单明细_{start_date:%Y%m%d}-{end_date:%Y%m%d}.xlsx"
    token = create_download_token(file, name, DOWNLOAD_EXPIRES)
    return {
        "row_count": len(df),
        "date_range": date_range,
        "columns": list(df.columns),
        "download_url": f"{settings.PUBLIC_BASE_URL}/export/download?token={token}",
        "expires_in_minutes": int(DOWNLOAD_EXPIRES.total_seconds() // 60),
        "summary": summary,
    }
