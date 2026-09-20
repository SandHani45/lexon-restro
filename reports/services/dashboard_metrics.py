# reports/services/dashboard_metrics.py
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Sum, Count, F
from django.utils import timezone

from orders.models import Order, Payment, Table
from inventory.models import InventoryItem
from tenants.models import Outlet
from core.utils import get_business_date, get_business_date_range


def owner_dashboard_metrics(user):
    tenant = user.tenant

    if user.role == "owner":
        outlets = list(Outlet.objects.filter(tenant=tenant))
    else:
        outlets = list(Outlet.objects.filter(id=user.outlet.id))

    # Each outlet can have its own business_day_start_hour, so "today" isn't
    # one shared date across a multi-outlet tenant — outlet A might already
    # be on the next business day while outlet B (opened later, or on a
    # later cutoff) is still on the previous one. A single shared
    # `today = localdate()` used for every outlet, and a plain
    # created_at__date= filter, meant any order placed after midnight but
    # before an outlet's cutoff hour vanished from that outlet's own
    # dashboard until the calendar caught up — the exact bug already found
    # and fixed in the Z-report, live here on the page an owner actually
    # watches all day.
    business_dates = {o.id: get_business_date(timezone.now(), o) for o in outlets}
    ranges = {o.id: get_business_date_range(business_dates[o.id], o) for o in outlets}

    cache_key = f"dashboard_metrics_{tenant.id}_{user.outlet_id}_" + "_".join(
        f"{oid}:{d}" for oid, d in sorted(business_dates.items())
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Low stock and kitchen queue are point-in-time, not "today" scoped —
    # still fine to batch across outlets. Everything "today"-scoped is
    # computed per-outlet below since each has its own business-day window.
    outlet_ids = [o.id for o in outlets]

    active_tables_qs = (
        Table.objects
        .filter(tenant=tenant, outlet_id__in=outlet_ids, state__in=["ordering", "preparing", "ready"])
        .values("outlet_id")
        .annotate(count=Count("id"))
    )
    tables_map = {t["outlet_id"]: t["count"] for t in active_tables_qs}

    kitchen_qs = (
        Order.objects
        .filter(
            tenant=tenant,
            outlet_id__in=outlet_ids,
            status__in=["open", "billing"],
            items__status__in=["sent", "preparing"],
        )
        .values("outlet_id")
        .annotate(count=Count("id", distinct=True))
    )
    kitchen_map = {k["outlet_id"]: k["count"] for k in kitchen_qs}

    low_stock_qs = (
        InventoryItem.objects
        .filter(tenant=tenant, outlet_id__in=outlet_ids, stock__lte=F("low_stock_threshold"))
        .values("outlet_id")
        .annotate(count=Count("id"))
    )
    stock_map = {s["outlet_id"]: s["count"] for s in low_stock_qs}

    # Assemble — each outlet queried with its own business-day window.
    results = []
    for outlet in outlets:
        start, end = ranges[outlet.id]

        rev = (
            Payment.objects
            .filter(order__tenant=tenant, order__outlet_id=outlet.id, paid_at__gte=start, paid_at__lt=end)
            .exclude(method="refund")
            .aggregate(total=Sum("amount"))["total"] or 0
        )
        orders = Order.objects.filter(
            tenant=tenant, outlet_id=outlet.id, created_at__gte=start, created_at__lt=end,
            status__in=["closed", "paid"],
        ).count()
        voids = Order.objects.filter(
            tenant=tenant, outlet_id=outlet.id, created_at__gte=start, created_at__lt=end,
            status="cancelled",
        ).count()
        disc = Order.objects.filter(
            tenant=tenant, outlet_id=outlet.id, created_at__gte=start, created_at__lt=end,
            discount_total__gt=0,
        ).aggregate(total=Sum("discount_total"), count=Count("id"))

        results.append({
            "outlet":          outlet.name,
            "revenue":         rev,
            "orders":          orders,
            "avg_order_value": (rev / orders) if orders else 0,
            "active_tables":   tables_map.get(outlet.id, 0),
            "kitchen_orders":  kitchen_map.get(outlet.id, 0),
            "low_stock":       stock_map.get(outlet.id, 0),
            "voids_today":     voids,
            "discounts_amount": disc["total"] or 0,
            "discounts_count":  disc["count"] or 0,
        })

    cache.set(cache_key, results, 60)  # 60-second TTL
    return results


def weekly_revenue_series(user):
    """
    Real daily revenue for the last 7 business days (oldest first, so the
    dashboard's Weekly Revenue chart can plot Mon..Sun style left-to-right)
    across every outlet the user can see -- an owner across all their
    outlets combined, a manager/cashier for just their own. Was previously
    a hand-drawn SVG with hardcoded bar heights and a fabricated "+15.4% vs
    last week" figure; both are now computed from real Payment rows.

    Returns {"days": [{"label": "Mon", "date": "2026-09-14", "revenue": 1234.0}, ...],
             "change_pct": 15.4 or None, "max_revenue": 1234.0}
    "change_pct" is this-7-days total vs the previous-7-days total; None
    when the previous period had zero revenue (percentage change is
    undefined against a zero base, not "infinite growth").
    """
    tenant = user.tenant
    if user.role == "owner":
        outlets = list(Outlet.objects.filter(tenant=tenant))
    else:
        outlets = [user.outlet] if user.outlet else []

    if not outlets:
        return {"days": [], "change_pct": None, "max_revenue": 0}

    cache_key = f"weekly_revenue_{tenant.id}_{user.outlet_id}_" + "_".join(
        str(get_business_date(timezone.now(), o)) for o in outlets
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def revenue_for_business_date(business_date):
        total = 0
        for outlet in outlets:
            start, end = get_business_date_range(business_date, outlet)
            total += (
                Payment.objects
                .filter(order__tenant=tenant, order__outlet=outlet, paid_at__gte=start, paid_at__lt=end)
                .exclude(method="refund")
                .aggregate(total=Sum("amount"))["total"] or 0
            )
        return float(total)

    today = get_business_date(timezone.now(), outlets[0])
    last_7_dates = [today - timedelta(days=i) for i in range(6, -1, -1)]
    days = [
        {"label": d.strftime("%a"), "date": d.isoformat(), "revenue": revenue_for_business_date(d)}
        for d in last_7_dates
    ]

    this_week_total = sum(d["revenue"] for d in days)
    prev_7_dates = [today - timedelta(days=i) for i in range(13, 6, -1)]
    prev_week_total = sum(revenue_for_business_date(d) for d in prev_7_dates)

    change_pct = (
        round((this_week_total - prev_week_total) / prev_week_total * 100, 1)
        if prev_week_total > 0 else None
    )

    max_revenue = max((d["revenue"] for d in days), default=0)
    peak_index = max(range(len(days)), key=lambda i: days[i]["revenue"]) if days and max_revenue > 0 else -1

    # SVG geometry precomputed here (not in the template) -- Django templates
    # have no arithmetic beyond `{% widthratio %}`, and doing 7 bars' worth
    # of proportional height/position math through that would be far less
    # readable than just handing the template ready-to-draw numbers, the
    # same way the chart's original hardcoded x/y/height values were plain
    # literals.
    chart_top, chart_bottom = 20, 140         # SVG y-coordinates of the gridlines
    bar_width = 44
    bar_xs = [70, 160, 250, 340, 430, 520, 610]  # matches the original hand-drawn spacing
    usable_height = chart_bottom - chart_top

    for i, d in enumerate(days):
        ratio = (d["revenue"] / max_revenue) if max_revenue > 0 else 0
        height = round(ratio * usable_height, 1)
        d["x"] = bar_xs[i] if i < len(bar_xs) else bar_xs[-1] + (i - len(bar_xs) + 1) * 90
        d["bar_width"] = bar_width
        d["height"] = height
        d["y"] = round(chart_bottom - height, 1)
        d["text_x"] = d["x"] + bar_width / 2
        d["is_peak"] = (i == peak_index)
        d["revenue_label"] = _compact_currency(d["revenue"])

    result = {
        "days": days,
        "change_pct": change_pct,
        "max_revenue": max_revenue,
        "max_revenue_label": _compact_currency(max_revenue),
        "mid_revenue_label": _compact_currency(max_revenue * 0.5),
        "three_quarter_revenue_label": _compact_currency(max_revenue * 0.75),
        "chart_top": chart_top,
        "chart_bottom": chart_bottom,
    }
    cache.set(cache_key, result, 300)  # 5-minute TTL -- this scans 14 business days, costlier than the 60s "today" metrics above
    return result


def _compact_currency(amount):
    """₹0, ₹850, ₹2.4k, ₹1.2L -- matches the original hardcoded chart's ₹2.0k-style labels."""
    amount = float(amount or 0)
    if amount >= 100000:
        return f"₹{amount / 100000:.1f}L"
    if amount >= 1000:
        return f"₹{amount / 1000:.1f}k"
    return f"₹{amount:.0f}"