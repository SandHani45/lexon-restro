"""Owner/manager dashboard and metrics."""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache

from core.decorators import tenant_required, role_required
from notifications.models import Notification
from reports.services.dashboard_metrics import owner_dashboard_metrics, weekly_revenue_series
from menu.models import MenuItem


@never_cache
@login_required
@tenant_required
@role_required("owner", "manager", "cashier")
def owner_dashboard(request):
    metrics       = owner_dashboard_metrics(request.user)
    weekly_revenue = weekly_revenue_series(request.user)
    notifications = Notification.objects.filter(
        tenant=request.user.tenant, outlet=request.user.outlet, is_read=False
    ).order_by("-created_at")[:10]

    from setup.models import AggregatorConfig
    aggregator_config, _ = AggregatorConfig.for_outlet(
        request.user.outlet, request.user.tenant)

    tenant = request.user.tenant
    is_qsr = tenant.tenant_type in ["franchise", "cafe"]

    from core.features import has_feature
    direct_billing_mode = is_qsr and has_feature(tenant, "direct_billing_mode")

    active_token_count = 0
    if is_qsr:
        from tokens.models import TokenOrder
        from core.utils import get_business_date
        from django.utils import timezone
        today = get_business_date(timezone.now(), request.user.outlet)
        active_token_count = TokenOrder.objects.filter(
            outlet=request.user.outlet, date=today,
            order__status__in=["open", "billing"],
        ).count()

    is_manager = request.user.role == "manager"
    is_cashier = request.user.role == "cashier"

    if is_cashier and not direct_billing_mode:
        return redirect("token-dashboard")

    if not request.session.get("onboarding_done") and not MenuItem.objects.filter(
        tenant=request.user.tenant, outlet=request.user.outlet
    ).exists():
        return redirect("/setup/onboard/")

    from orders.models import Order, OrderItem
    from django.db.models import Sum

    recent_orders = list(
        Order.objects.filter(tenant=tenant, outlet=request.user.outlet)
        .select_related("table")
        .order_by("-created_at")[:6]
    )

    from django.db.models import F

    top_items = list(
        OrderItem.objects.filter(
            order__tenant=tenant,
            order__outlet=request.user.outlet,
            menu_item__isnull=False,
        )
        .values(item_name=F("menu_item__name"))
        .annotate(total_qty=Sum("quantity"))
        .order_by("-total_qty")[:5]
    )

    today_reservations = []
    res_confirmed_count = 0
    try:
        from crm.models import Reservation
        today_reservations = list(
            Reservation.objects.filter(
                tenant=tenant, outlet=request.user.outlet
            ).select_related("guest", "table").order_by("-reservation_time")[:5]
        )
        res_confirmed_count = sum(1 for r in today_reservations if r.status == "confirmed")
    except Exception:
        pass

    return render(request, "accounts/owner_dashboard.html", {
        "metrics":             metrics,
        "weekly_revenue":      weekly_revenue,
        "notifications":       notifications,
        "aggregator":          aggregator_config,
        "is_qsr":              is_qsr,
        "direct_billing_mode": direct_billing_mode,
        "active_token_count":  active_token_count,
        "is_manager":          is_manager,
        "is_cashier":          is_cashier,
        "recent_orders":       recent_orders,
        "top_items":           top_items,
        "today_reservations":  today_reservations,
        "res_confirmed_count": res_confirmed_count,
    })


@login_required
@tenant_required
def dashboard_metrics_json(request):
    if request.user.role not in ["owner", "manager", "cashier"]:
        return JsonResponse({"error": "forbidden"}, status=403)
    metrics = owner_dashboard_metrics(request.user)
    return JsonResponse({"metrics": metrics})


@login_required
def sales_dashboard(request):
    """Reseller view — superuser sees all tenants; agents see their own."""
    from tenants.models import Tenant
    from accounts.models import User
    from django.contrib import messages
    from django.shortcuts import redirect

    if request.method == "POST" and request.user.is_superuser:
        action = request.POST.get("action")
        if action == "add_client":
            name     = request.POST.get("name")
            agent_id = request.POST.get("agent_id")
            if name:
                agent = User.objects.filter(id=agent_id).first() if agent_id else None
                Tenant.objects.create(name=name, sales_agent=agent)
                messages.success(request, f"Client {name} added.")
        elif action == "allocate_client":
            tenant_id = request.POST.get("tenant_id")
            agent_id  = request.POST.get("agent_id")
            tenant    = Tenant.objects.filter(id=tenant_id).first()
            if tenant:
                tenant.sales_agent = User.objects.filter(id=agent_id).first() if agent_id else None
                tenant.save()
                messages.success(request, f"Updated allocation for {tenant.name}.")
        elif action == "delete_client":
            tenant_id = request.POST.get("tenant_id")
            tenant    = Tenant.objects.filter(id=tenant_id).first()
            if tenant:
                tenant.is_active = False
                tenant.save(update_fields=["is_active"])
                messages.success(request, f"{tenant.name} deactivated.")
        return redirect("sales_dashboard")

    if request.user.is_superuser:
        clients = Tenant.objects.all().select_related("sales_agent")
        agents  = User.objects.filter(is_superuser=False)
    else:
        clients = Tenant.objects.filter(sales_agent=request.user)
        agents  = []
        if not clients.exists():
            return redirect("dashboard")

    return render(request, "accounts/sales_dashboard.html", {"clients": clients, "agents": agents})
