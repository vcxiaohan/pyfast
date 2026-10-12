from fastmcp.exceptions import ToolError
from sqlalchemy import select

from models import AsyncSessionFactory
from models.mall import MallOrder, Product, Shop


async def get_order_detail(order_no: str) -> dict:
    """按订单号查询订单详情：店铺、商品、数量、实付金额（元）、状态、来源渠道、下单时间、支付时间。

    用于排查客诉，比如“用户说已付款但订单显示待支付”：对比 status 和 paid_time 是否矛盾。
    """
    async with AsyncSessionFactory() as session:
        async with session.begin():
            row = (
                await session.execute(
                    select(MallOrder, Product.name, Shop.name)
                    .join(Product, Product.id == MallOrder.product_id)
                    .join(Shop, Shop.id == MallOrder.shop_id)
                    .where(MallOrder.order_no == order_no.strip())
                )
            ).one_or_none()

    # ToolError 的消息会原样返回给模型；抛其他异常会被包成“Error calling tool …”
    if row is None:
        raise ToolError("订单不存在")

    order, product_name, shop_name = row
    return {
        "order_no": order.order_no,
        "shop_name": shop_name,
        "product_name": product_name,
        "quantity": order.quantity,
        "amount": order.amount / 100,
        "status": order.status,
        "utm_source": order.utm_source,
        "buyer_phone": f"{order.buyer_phone[:3]}****{order.buyer_phone[-4:]}",
        "create_time": str(order.create_time),
        "paid_time": str(order.paid_time) if order.paid_time else None,
    }
