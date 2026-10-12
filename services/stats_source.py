"""运营统计数据源：概览、趋势、排行都通过这里拿聚合好的数字，不关心数据从哪来。

真实环境里统计归下游的数据服务管，这里应该调它的统计接口，例如
GET /stats?start_date=2026-10-06&end_date=2026-10-12&dims=date,utm_source&utm_source=douyin，
按维度分组返回原始的单数和金额（分）。demo 没有下游服务，用本地库模拟同样的输入输出；
以后接真实接口只改这个文件，工具和前端都不用动。

统计口径和导出的统计摘要一致：按下单时间筛选，已支付、已发货、已完成算成交。
"""

from typing import Literal

from sqlalchemy import Date, cast, func, select

from models import AsyncSessionFactory
from models.mall import MallOrder, Product, Shop
from services.export_service import DEAL_STATUSES
from services.order_source import OrderQuery, filter_orders

StatsDim = Literal["date", "utm_source", "shop", "product"]

_DIM_COLUMNS = {
    "date": cast(MallOrder.create_time, Date),
    "utm_source": MallOrder.utm_source,
    "shop": Shop.name,
    "product": Product.name,
}


async def query_stats(query: OrderQuery, dims: list[StatsDim]) -> list[dict]:
    """每个分组一行：维度的值，加上 order_count、deal_count、deal_amount（分）、refund_count。

    dims 为空时只返回一行汇总。没有订单的分组不会出现在结果里，例如某天没订单就没有这天的行。
    """
    deal = MallOrder.status.in_(DEAL_STATUSES)
    stmt = filter_orders(
        select(
            *(_DIM_COLUMNS[dim].label(dim) for dim in dims),
            func.count().label("order_count"),
            func.count().filter(deal).label("deal_count"),
            func.coalesce(func.sum(MallOrder.amount).filter(deal), 0).label("deal_amount"),
            func.count().filter(MallOrder.status == "refunded").label("refund_count"),
        ),
        query,
    ).group_by(*(_DIM_COLUMNS[dim] for dim in dims))
    async with AsyncSessionFactory() as session:
        rows = (await session.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]
