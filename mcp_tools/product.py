from pydantic import BaseModel, Field
from sqlalchemy import select

from models import AsyncSessionFactory
from models.mall import Product


class ProductItem(BaseModel):
    name: str = Field(description="商品名称")
    price: float = Field(description="商品售价，单位元")


async def get_all_products() -> list[ProductItem]:
    """查询所有商品的名称和售价（元）。"""
    async with AsyncSessionFactory() as session:
        async with session.begin():
            rows = (await session.execute(select(Product.name, Product.price))).all()
    return [ProductItem(name=name, price=price / 100) for name, price in rows]
