"""运营指标查询：概览、趋势、排行，结果在助手里显示成指标卡和图表。

数据来自下游统计接口，这里只做参数校验、算比率、补齐日期，再拼成画图用的数据。
图怎么画由前端决定，模型不经手图表配置：图上的数字就是接口返回的数字，不会被模型抄错。
"""

import asyncio
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastmcp.exceptions import ToolError

from services.export_service import CHANNEL_LABELS, MAX_DAYS
from services.order_source import OrderQuery
from services.stats_source import query_stats

Metric = Literal["order_count", "deal_count", "deal_amount", "avg_order_amount", "refund_count", "refund_rate"]
Channel = Literal["douyin", "kuaishou", "gdt", "natural"]

# 指标的中文名和单位
METRICS: dict[str, tuple[str, str]] = {
    "order_count": ("下单数", "单"),
    "deal_count": ("成交单数", "单"),
    "deal_amount": ("成交额", "元"),
    "avg_order_amount": ("客单价", "元"),
    "refund_count": ("退款单数", "单"),
    "refund_rate": ("退款率", "%"),
}
DIMENSION_LABELS = {"utm_source": "渠道", "shop": "店铺", "product": "商品"}
OVERVIEW_METRICS: list[Metric] = ["deal_amount", "deal_count", "avg_order_amount", "refund_rate"]
MAX_RANKING = 20


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def _resolve_range(start_date: date | None, end_date: date | None) -> tuple[date, date]:
    start_date = start_date or end_date or _today()
    end_date = end_date or start_date
    if start_date > end_date:
        raise ToolError("开始日期不能晚于结束日期")
    if (end_date - start_date).days + 1 > MAX_DAYS:
        raise ToolError(f"一次最多查 {MAX_DAYS} 天，请缩小时间范围")
    return start_date, end_date


def _value(row: dict, metric: Metric) -> float:
    """下游只给原始单数和金额（分），金额换算、客单价、退款率在这里算。"""
    deal_count, refund_count = row["deal_count"], row["refund_count"]
    if metric == "deal_amount":
        return round(row["deal_amount"] / 100, 2)
    if metric == "avg_order_amount":
        return round(row["deal_amount"] / 100 / deal_count, 2) if deal_count else 0
    if metric == "refund_rate":
        # 和导出的统计摘要同一个口径：退款单 / 付过款的单
        paid_count = deal_count + refund_count
        return round(refund_count / paid_count * 100, 1) if paid_count else 0
    return row[metric]


def _change(metric: Metric, current: float, previous: float) -> str:
    # 退款率本身是百分比，涨跌说“几个百分点”，说“涨了 20%”会让人误解
    if metric == "refund_rate":
        return f"{current - previous:+.1f} 个百分点"
    return f"{(current - previous) / previous:+.1%}" if previous else "—"


def _name(dimension: str, key: str) -> str:
    return CHANNEL_LABELS.get(key, key) if dimension == "utm_source" else key


def _title(utm_source: str | None, shop_name: str | None, text: str) -> str:
    scope = "·".join(part for part in [CHANNEL_LABELS.get(utm_source or ""), shop_name] if part)
    return f"{scope} {text}" if scope else text


async def query_overview(
        start_date: date | None = None,
        end_date: date | None = None,
        utm_source: Channel | None = None,
        shop_name: str | None = None,
) -> dict:
    """查一段时间的核心指标：成交额、成交单数、客单价、退款率，并和前一个同样长度的时间段对比。

    - 用户问“今天卖得怎么样”“这周整体情况”这类整体数据时用它，结果显示成指标卡。
    - 没说日期时默认今天；只说了一天就把 start_date 和 end_date 都设成那天。
    - utm_source 渠道：douyin 抖音、kuaishou 快手、gdt 广点通、natural 自然流量。
    - 按下单时间统计，已支付、已发货、已完成算成交。
    """
    start_date, end_date = _resolve_range(start_date, end_date)
    days = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    filters = {"utm_source": utm_source, "shop_name": shop_name}
    [current], [previous] = await asyncio.gather(
        query_stats(OrderQuery(start_date=start_date, end_date=end_date, **filters), []),
        query_stats(OrderQuery(start_date=previous_end - timedelta(days=days - 1), end_date=previous_end, **filters), []),
    )

    metrics = []
    for metric in OVERVIEW_METRICS:
        label, unit = METRICS[metric]
        value = _value(current, metric)
        change = _change(metric, value, _value(previous, metric)) if previous["order_count"] else "—"
        metrics.append({"label": label, "value": value, "unit": unit, "change": change})
    return {
        "title": _title(utm_source, shop_name, "核心指标"),
        "date_range": f"{start_date} ~ {end_date}",
        "compare_label": "较前一天" if days == 1 else f"较前 {days} 天",
        "metrics": metrics,
    }


async def query_trend(
        metric: Metric,
        start_date: date | None = None,
        end_date: date | None = None,
        group_by: Literal["utm_source", "shop"] | None = None,
        utm_source: Channel | None = None,
        shop_name: str | None = None,
        chart: Literal["line", "bar"] = "line",
) -> dict:
    """按天查某个指标的变化，结果画成折线图或柱状图。

    - 用户问每天的走势、变化，或者要求“画出来”时用它。没说日期时默认最近 7 天（含今天）。
    - metric：order_count 下单数（订单量）、deal_count 成交单数、deal_amount 成交额、
      avg_order_amount 客单价、refund_count 退款单数、refund_rate 退款率。
    - group_by：要按渠道或店铺拆成多条线对比时传，不拆就不传。
    - chart：用户要柱状图传 bar，其他情况用 line。
    - utm_source 渠道：douyin 抖音、kuaishou 快手、gdt 广点通、natural 自然流量。
    """
    if not start_date and not end_date:
        start_date, end_date = _today() - timedelta(days=6), _today()
    start_date, end_date = _resolve_range(start_date, end_date)
    query = OrderQuery(start_date=start_date, end_date=end_date, utm_source=utm_source, shop_name=shop_name)
    rows = await query_stats(query, ["date", group_by] if group_by else ["date"])

    label, unit = METRICS[metric]
    groups: dict[str, dict[date, dict]] = {}
    for row in rows:
        name = _name(group_by, row[group_by]) if group_by else label
        groups.setdefault(name, {})[row["date"]] = row
    if not group_by:
        groups.setdefault(label, {})

    # 下游只返回有订单的日期，没订单的日期补 0，不然这一天在图上直接没了
    dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    series = [
        {"name": name, "data": [_value(by_date[d], metric) if d in by_date else 0 for d in dates]}
        for name, by_date in groups.items()
    ]
    series.sort(key=lambda s: sum(s["data"]), reverse=True)
    suffix = f"（按{DIMENSION_LABELS[group_by]}）" if group_by else ""
    return {
        "chart": chart,
        "title": _title(utm_source, shop_name, f"{label}趋势{suffix}"),
        "date_range": f"{start_date} ~ {end_date}",
        "unit": unit,
        "x": [d.strftime("%m-%d") for d in dates],
        "series": series,
    }


async def query_ranking(
        metric: Metric,
        dimension: Literal["utm_source", "shop", "product"],
        start_date: date | None = None,
        end_date: date | None = None,
        utm_source: Channel | None = None,
        shop_name: str | None = None,
        limit: int = 10,
) -> dict:
    """按渠道、店铺或商品对比某个指标，从高到低排，结果画成横向柱状图。

    - 用户问“哪个渠道卖得最好”“各店铺成交额对比”“退款最多的商品”时用它。
    - 没说日期时默认今天；只说了一天就把 start_date 和 end_date 都设成那天。
    - metric 的含义同 query_trend；dimension：utm_source 渠道、shop 店铺、product 商品。
    - limit 只看前几名，最多 20。
    """
    start_date, end_date = _resolve_range(start_date, end_date)
    query = OrderQuery(start_date=start_date, end_date=end_date, utm_source=utm_source, shop_name=shop_name)
    rows = await query_stats(query, [dimension])

    label, unit = METRICS[metric]
    items = [(_name(dimension, row[dimension]), _value(row, metric)) for row in rows]
    items.sort(key=lambda item: item[1], reverse=True)
    items = items[: max(1, min(limit, MAX_RANKING))]
    return {
        "chart": "bar",
        "horizontal": True,
        "title": _title(utm_source, shop_name, f"各{DIMENSION_LABELS[dimension]}{label}"),
        "date_range": f"{start_date} ~ {end_date}",
        "unit": unit,
        "x": [name for name, _ in items],
        "series": [{"name": label, "data": [value for _, value in items]}],
    }
