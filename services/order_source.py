"""订单数据源：导出只通过这里拿订单，不关心数据从哪来。

真实环境里订单归下游的订单服务管，这里应该调它的分页列表接口，例如 GET /orders?page=1&size=1000，
返回 {"list": [...], "total": N}。demo 没有下游服务，用本地库模拟同样的输入输出；
以后接真实接口只改这个文件，worker 和工具都不用动。
"""

from datetime import date, datetime, time, timedelta

from pydantic import BaseModel
from sqlalchemy import func, select

from models import AsyncSessionFactory
from models.mall import MallOrder, Product, Shop


class OrderQuery(BaseModel):
    start_date: date
    end_date: date
    utm_source: str | None = None
    status: str | None = None
    shop_name: str | None = None


# 下游接口返回的每条订单都有这些字段，导出时再挑用户要的列
_COLUMNS = {
    "order_no": MallOrder.order_no,
    "shop_name": Shop.name,
    "product_name": Product.name,
    "quantity": MallOrder.quantity,
    "amount": MallOrder.amount,
    "status": MallOrder.status,
    "utm_source": MallOrder.utm_source,
    "buyer_phone": MallOrder.buyer_phone,
    "create_time": MallOrder.create_time,
    "paid_time": MallOrder.paid_time,
}


def _filter(stmt, query: OrderQuery):
    stmt = (
        stmt.select_from(MallOrder)
        .join(Product, Product.id == MallOrder.product_id)
        .join(Shop, Shop.id == MallOrder.shop_id)
        .where(
            MallOrder.create_time >= datetime.combine(query.start_date, time.min),
            MallOrder.create_time < datetime.combine(query.end_date + timedelta(days=1), time.min),
        )
    )
    if query.utm_source:
        stmt = stmt.where(MallOrder.utm_source == query.utm_source)
    if query.status:
        stmt = stmt.where(MallOrder.status == query.status)
    if query.shop_name:
        stmt = stmt.where(Shop.name.contains(query.shop_name))
    return stmt


async def list_orders(query: OrderQuery, page: int, size: int) -> tuple[list[dict], int]:
    """按下单时间分页查订单，返回 (这一页的订单, 总条数)。page 从 1 开始。"""
    async with AsyncSessionFactory() as session:
        total = await session.scalar(_filter(select(func.count()), query))
        # 加上 id 排序：下单时间相同的订单顺序固定，翻页时不会漏行或重复
        stmt = (
            _filter(select(*_COLUMNS.values()), query)
            .order_by(MallOrder.create_time, MallOrder.id)
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = (await session.execute(stmt)).all()
    return [dict(zip(_COLUMNS, row)) for row in rows], total or 0
