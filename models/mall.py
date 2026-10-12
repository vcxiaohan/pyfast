"""运营数据助手用的演示电商数据：店铺、商品、订单、流量、广告。

金额一律存“分”（整数），展示时再换算成元，避免浮点误差。
时间一律存北京时间（不带时区），统计“某一天”按北京时间的 0 点到 24 点算。
"""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class OrderStatus(StrEnum):
    PENDING = "pending"  # 待支付
    PAID = "paid"  # 已支付，待发货
    SHIPPED = "shipped"  # 已发货
    COMPLETED = "completed"  # 已完成
    REFUNDED = "refunded"  # 已退款
    CANCELLED = "cancelled"  # 已取消：超时未支付


class Shop(Base):
    __tablename__ = "mall_shop"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), comment="店铺名")


# 用户能看哪些店铺的数据。管理员不用绑定，能看全部
class UserShop(Base):
    __tablename__ = "mall_user_shop"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("mall_shop.id", ondelete="CASCADE"), primary_key=True)


class Product(Base):
    __tablename__ = "mall_product"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("mall_shop.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    price: Mapped[int] = mapped_column(Integer, comment="售价，单位分")


# 投放电商的落地页一般一单只买一个商品，所以订单上直接记商品，不再拆订单明细表
class MallOrder(Base):
    __tablename__ = "mall_order"
    # 统计都是“某店铺某段时间支付的订单”，所以建 (shop_id, paid_time) 联合索引
    __table_args__ = (Index("ix_mall_order_shop_id_paid_time", "shop_id", "paid_time"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, comment="订单号")
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("mall_shop.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("mall_product.id", ondelete="RESTRICT"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    amount: Mapped[int] = mapped_column(Integer, comment="实付金额，单位分")
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.PENDING, comment="状态")
    utm_source: Mapped[str] = mapped_column(String(20), comment="来源渠道：douyin、kuaishou、gdt、natural")
    buyer_phone: Mapped[str] = mapped_column(String(20), comment="买家手机号，对外展示时必须脱敏")
    paid_time: Mapped[datetime | None] = mapped_column(DateTime, comment="支付时间，未支付为 NULL")


class ShopTraffic(Base):
    __tablename__ = "mall_shop_traffic"
    __table_args__ = (UniqueConstraint("shop_id", "stat_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("mall_shop.id", ondelete="CASCADE"))
    stat_date: Mapped[date] = mapped_column(Date, comment="统计日期")
    visitor_count: Mapped[int] = mapped_column(Integer, comment="访客数")


# 每天每个渠道一行，由广告平台的报表同步过来；自然流量没有广告花费，不在这张表里
class AdStat(Base):
    __tablename__ = "mall_ad_stat"
    __table_args__ = (UniqueConstraint("shop_id", "stat_date", "utm_source"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, ForeignKey("mall_shop.id", ondelete="CASCADE"))
    stat_date: Mapped[date] = mapped_column(Date, comment="统计日期")
    utm_source: Mapped[str] = mapped_column(String(20), comment="渠道")
    cost: Mapped[int] = mapped_column(Integer, comment="广告花费，单位分")
    impressions: Mapped[int] = mapped_column(Integer, comment="曝光数")
    clicks: Mapped[int] = mapped_column(Integer, comment="点击数")
