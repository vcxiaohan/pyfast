"""重置运营数据助手的演示数据：只清空并重建 mall_ 开头的表，不动用户和文章。

在 pyfast 目录下执行：python init_mall_data.py
必须先执行过 init_data.py（要用到里面的用户）。init_data.py 会清空所有表，包括这里的 mall_ 表，
所以每次跑完 init_data.py 都要再跑一次本脚本。

造的数据：3 个店铺、每店 4 个商品、最近 30 天加今天的订单、每天的访客数和各渠道广告数据。
随机数用固定种子，同一天执行结果一样；日期按执行当天往前推，隔天执行数字会不同。
权限：管理员能看全部店铺，张三只能看店铺 1，李四只能看店铺 2，王五一个都没绑，用来演示无权限。
另外埋了两处演示数据：
- 店铺 1 昨天抖音渠道的 ROI 明显下滑，演示“哪个渠道掉了”
- 店铺 1 昨天有一个已支付、但状态还是待支付的订单，演示客诉排查，订单号在执行完后打印
"""

import asyncio
import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select, text

from models import AsyncSessionFactory, engine
from models.mall import AdStat, MallOrder, OrderStatus, Product, Shop, ShopTraffic, UserShop
from models.user import User

DAYS = 30

# (店铺名, 流量规模, [(商品名, 售价分)])
SHOPS = [
    ("优选好物旗舰店", 1.0, [("便携榨汁杯", 8900), ("颈椎按摩仪", 15900), ("车载香薰", 3990), ("折叠收纳箱", 4590)]),
    ("鲜果日记", 0.7, [("赣南脐橙 5 斤", 3990), ("海南贵妃芒 3 斤", 4590), ("阳光玫瑰葡萄 2 斤", 5990), ("烟台红富士 10 斤", 6990)]),
    ("居家百货店", 0.5, [("加厚垃圾袋 200 只", 1990), ("厨房湿巾 6 包", 2490), ("硅藻泥地垫", 3590), ("真空压缩袋 10 件套", 4990)]),
]

# 投放为主，自然流量占小头
CHANNEL_WEIGHTS = {"douyin": 0.45, "kuaishou": 0.25, "gdt": 0.15, "natural": 0.15}
ROI_RANGE = {"douyin": (2.0, 3.2), "kuaishou": (1.6, 2.6), "gdt": (1.2, 2.2)}
ANOMALY_ROI_RANGE = (0.6, 0.9)

MALL_TABLES = [UserShop, AdStat, ShopTraffic, MallOrder, Product, Shop]


def random_phone(rng: random.Random) -> str:
    return "1" + rng.choice("3456789") + "".join(rng.choices("0123456789", k=9))


def pick_status(rng: random.Random, created: datetime, days_ago: int, now: datetime) -> tuple[str, datetime | None]:
    roll = rng.random()
    if roll < 0.10:
        return OrderStatus.CANCELLED, None
    if days_ago == 0 and roll < 0.18:
        return OrderStatus.PENDING, None

    paid_time = created + timedelta(seconds=rng.randint(20, 600))
    if paid_time > now:
        return OrderStatus.PENDING, None
    if rng.random() < 0.06:
        return OrderStatus.REFUNDED, paid_time
    if days_ago <= 1:
        return OrderStatus.PAID, paid_time
    if days_ago <= 5:
        return OrderStatus.SHIPPED, paid_time
    return OrderStatus.COMPLETED, paid_time


def build_day(
    rng: random.Random,
    shop: Shop,
    scale: float,
    products: list[Product],
    day: date,
    days_ago: int,
    now: datetime,
) -> tuple[list[dict], dict, list[dict]]:
    """生成某店铺某一天的订单、访客数和广告数据。"""
    day_start = datetime.combine(day, time.min)
    # 今天只造到当前时刻为止的数据
    seconds_in_day = 86400 if days_ago > 0 else max(int((now - day_start).total_seconds()), 1)
    visitor_count = int(rng.randint(1200, 2200) * scale * seconds_in_day / 86400)
    order_count = int(visitor_count * rng.uniform(0.025, 0.045))

    orders = []
    paid_by_channel = {source: [0, 0] for source in CHANNEL_WEIGHTS}
    for seq in range(1, order_count + 1):
        created = day_start + timedelta(seconds=rng.randrange(seconds_in_day))
        product = rng.choice(products)
        quantity = 1 if rng.random() < 0.9 else 2
        source = rng.choices(list(CHANNEL_WEIGHTS), weights=list(CHANNEL_WEIGHTS.values()))[0]
        status, paid_time = pick_status(rng, created, days_ago, now)
        amount = product.price * quantity
        orders.append(
            {
                "order_no": f"{day:%Y%m%d}{shop.id:02d}{seq:05d}",
                "shop_id": shop.id,
                "product_id": product.id,
                "quantity": quantity,
                "amount": amount,
                "status": status,
                "utm_source": source,
                "buyer_phone": random_phone(rng),
                "paid_time": paid_time,
                "create_time": created,
            }
        )
        if paid_time:
            paid_by_channel[source][0] += 1
            paid_by_channel[source][1] += amount

    traffic = {"shop_id": shop.id, "stat_date": day, "visitor_count": visitor_count}

    ad_stats = []
    for source, (paid_count, gmv) in paid_by_channel.items():
        if source == "natural":
            continue
        is_anomaly = shop.id == 1 and days_ago == 1 and source == "douyin"
        roi = rng.uniform(*(ANOMALY_ROI_RANGE if is_anomaly else ROI_RANGE[source]))
        cost = int(gmv / roi) if gmv else rng.randint(5000, 20000)
        clicks = int(paid_count / rng.uniform(0.02, 0.04)) if paid_count else rng.randint(50, 200)
        impressions = int(clicks / rng.uniform(0.01, 0.03))
        ad_stats.append(
            {
                "shop_id": shop.id,
                "stat_date": day,
                "utm_source": source,
                "cost": cost,
                "impressions": impressions,
                "clicks": clicks,
            }
        )
    return orders, traffic, ad_stats


async def init_mall_data():
    rng = random.Random(42)
    # 库里存的是不带时区的北京时间
    now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    today = now.date()

    async with AsyncSessionFactory() as session:
        async with session.begin():
            users = {u.email: u for u in await session.scalars(select(User))}
            zhangsan, lisi = users.get("zhangsan@test.com"), users.get("lisi@test.com")
            if zhangsan is None or lisi is None:
                print("找不到张三或李四，请先执行 python init_data.py")
                return

            # 表名来自模型定义而不是用户输入，拼 SQL 没有注入风险
            tables = ", ".join(f'"{model.__tablename__}"' for model in MALL_TABLES)
            await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY"))

            shops = [Shop(name=name) for name, _, _ in SHOPS]
            session.add_all(shops)
            await session.flush()

            products_by_shop = {}
            for shop, (_, _, product_specs) in zip(shops, SHOPS):
                products = [Product(shop_id=shop.id, name=name, price=price) for name, price in product_specs]
                session.add_all(products)
                products_by_shop[shop.id] = products
            await session.flush()

            session.add_all(
                [UserShop(user_id=zhangsan.id, shop_id=shops[0].id), UserShop(user_id=lisi.id, shop_id=shops[1].id)]
            )

            order_rows, traffic_rows, ad_rows = [], [], []
            for shop, (_, scale, _) in zip(shops, SHOPS):
                for days_ago in range(DAYS, -1, -1):
                    day = today - timedelta(days=days_ago)
                    orders, traffic, ad_stats = build_day(
                        rng, shop, scale, products_by_shop[shop.id], day, days_ago, now
                    )
                    order_rows += orders
                    traffic_rows.append(traffic)
                    ad_rows += ad_stats

            # 演示客诉：店铺 1 昨天的一个已支付订单，状态没更新，还是待支付
            yesterday_prefix = f"{today - timedelta(days=1):%Y%m%d}{shops[0].id:02d}"
            bug_order = next(
                row
                for row in order_rows
                if row["order_no"].startswith(yesterday_prefix) and row["status"] == OrderStatus.PAID
            )
            bug_order["status"] = OrderStatus.PENDING

            # 几千行数据用批量插入，比逐个 add 快得多
            await session.execute(insert(MallOrder), order_rows)
            await session.execute(insert(ShopTraffic), traffic_rows)
            await session.execute(insert(AdStat), ad_rows)

    print(f"已重建 {tables}")
    print(f"店铺 {len(shops)} 个，订单 {len(order_rows)} 条，流量 {len(traffic_rows)} 条，广告 {len(ad_rows)} 条")
    print(f"演示客诉的订单号：{bug_order['order_no']}（已支付，状态却是待支付）")


async def main():
    await init_mall_data()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
