# orders/views/billing_core.py
import logging
from decimal import Decimal

import json

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Sum, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from core.decorators import tenant_required
from core.features import has_feature
from menu.models import MenuCategory, MenuItem
from orders.models import Order, Table, Payment
from tablemerge.models import TableMerge
from orders.services.order_lock_service import lock_order
from setup.models import PaymentConfig

logger = logging.getLogger("pos.orders")


# -------------------------------------------------
# BILLING PAGE
# -------------------------------------------------

@login_required
@tenant_required
def billing_view(request):
    """
    Renders the main POS billing interface for staff.
    Handles table merging logic and enforces optimistic locking to prevent
    concurrent edits by multiple staff members on the same order.
    """
    table_id = request.GET.get("table")
    order = None

    if table_id:
        merge = (
            TableMerge.objects
            .filter(tenant=request.user.tenant, outlet=request.user.outlet,
                    is_active=True, tables__id=table_id)
            .select_related("primary_table").first()
        )
        if merge and str(table_id) != str(merge.primary_table.id):
            table_id = merge.primary_table.id

    if table_id:
        order = (
            Order.objects
            .filter(tenant=request.user.tenant, outlet=request.user.outlet,
                    table_id=table_id, status__in=["open", "billing"])
            .select_related("table", "lock").first()
        )

    if order:
        locked, locked_user = lock_order(order, request.user)
        if not locked:
            return render(request, "orders/order_locked.html", {"locked_by": locked_user, "order": order})

    categories = (
        MenuCategory.objects
        .filter(tenant=request.user.tenant, outlet=request.user.outlet, is_active=True)
        .prefetch_related(Prefetch("items", queryset=MenuItem.objects.filter(is_available=True)))
    )

    tables = Table.objects.filter(
        tenant=request.user.tenant, outlet=request.user.outlet, is_active=True
    ).order_by("name")

    from core.features import has_feature
    from setup.models import KitchenStation
    tenant = request.user.tenant
    outlet = request.user.outlet

    has_kds        = has_feature(tenant, "kitchen_display")
    has_kt_printer = KitchenStation.objects.filter(
        tenant=tenant, outlet=outlet, is_active=True, is_default=False
    ).exclude(printer_ip__isnull=True).exclude(printer_ip="").exists()

    # auto_kot_mode: no KDS screen AND no separate kitchen printer
    # → KOT is created at payment time and prints together with the bill
    # → customer carries the combined slip to the food counter
    auto_kot_mode = not has_kds and not has_kt_printer

    default_station = KitchenStation.objects.filter(
        tenant=tenant, outlet=outlet, is_active=True
    ).exclude(printer_ip__isnull=True).exclude(printer_ip="").first()

    return render(request, "orders/billing.html", {
        "categories":      categories,
        "tables":          tables,
        "order":           order,
        "selected_table":  table_id,
        "auto_kot_mode":   auto_kot_mode,
        "outlet":          request.user.outlet,
        "station_printer_ip": default_station.printer_ip if default_station else "",
    })


# -------------------------------------------------
# BILL VIEW
# -------------------------------------------------

@never_cache
@login_required
@tenant_required
def bill_view(request, order_id):
    """
    Renders the billing detail page for a specific order.
    Calculates remaining balance dynamically based on existing payments
    and handles table state transitions.
    """
    try:

        order = Order.objects.get(
            id=order_id, tenant=request.user.tenant, outlet=request.user.outlet
        )

        # Only while the order is still actually awaiting payment -- once
        # it's paid/closed/cancelled, this page reloads on its own right
        # after payment (to trigger printing) and must not undo the
        # "cleaning" state pay_order already correctly set a moment earlier.
        if order.table and order.status in ("open", "billing"):
            order.table.state = "billing"
            order.table.save(update_fields=["state"])

        # Get payment configuration
        config, _ = PaymentConfig.for_outlet(request.user.outlet, request.user.tenant)

        # Calculate remaining balance
        total_paid = order.payments.exclude(method="refund").aggregate(total=Sum("amount"))["total"] or Decimal("0")
        remaining = order.grand_total - total_paid

        # Available promos
        from promos.models import Promo
        promos = Promo.objects.filter(
            tenant=request.user.tenant,
            is_active=True
        ).filter(Q(outlet=request.user.outlet) | Q(outlet__isnull=True))

        valid_promos = [p for p in promos if p.is_currently_valid]

        from core.features import has_feature
        from setup.services.station_service import get_default_station
        tenant = request.user.tenant
        direct_billing_mode = has_feature(tenant, "direct_billing_mode")
        razorpay_feature_enabled = has_feature(tenant, "razorpay_gateway")
        is_qsr        = tenant.tenant_type in ("franchise", "cafe")
        gst_inclusive  = getattr(order.outlet, "gst_inclusive", False)
        is_composition = getattr(order.outlet, "is_composition_scheme", False)

        station = get_default_station(request.user)
        paper_width_mm = station.paper_width_mm if station else 80

        # Auto-print: after payment reload, pass print=1 so template opens receipt
        auto_print = request.GET.get("print") == "1"

        return render(request, "orders/bill.html", {
            "order": order,
            "config": config,
            "remaining": remaining,
            "total_paid": total_paid,
            "promos": valid_promos,
            "direct_billing_mode": direct_billing_mode,
            "razorpay_feature_enabled": razorpay_feature_enabled,
            "is_qsr":        is_qsr,
            "gst_inclusive":  gst_inclusive,
            "is_composition": is_composition,
            "paper_width_mm":  paper_width_mm,
            "auto_print":      auto_print,
            "default_station": station,
        })
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)


# -------------------------------------------------
# SEND BILL TO WHATSAPP (manual, from the bill screen)
# -------------------------------------------------

@login_required
@tenant_required
@require_POST
def send_whatsapp_bill(request, order_id):
    """
    Cashier-triggered "Send to WhatsApp" on the bill screen. Distinct from
    the automatic receipt fired on payment (payment_views.py) -- this lets
    staff (re-)send on demand, to a number typed in on the spot if the
    order has none on file yet, or to resend after the customer says they
    never got it. Runs synchronously (unlike the payment-flow send, which
    is deliberately async so it can't delay the "payment complete"
    response) because a cashier who just clicked the button is already
    waiting for a yes/no answer.
    """
    try:
        order = Order.objects.get(
            id=order_id, tenant=request.user.tenant, outlet=request.user.outlet
        )
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    if not has_feature(request.user.tenant, "whatsapp_receipts"):
        return JsonResponse({"error": "WhatsApp receipts aren't enabled for your account."}, status=403)

    from django.conf import settings
    if not (getattr(settings, "META_WHATSAPP_TOKEN", "") or getattr(settings, "TWILIO_ACCOUNT_SID", "")):
        return JsonResponse({"error": "WhatsApp sending isn't set up for this account yet. Contact support."}, status=503)

    try:
        body = json.loads(request.body or "{}")
    except ValueError:
        body = {}

    from notifications.services.whatsapp_service import send_bill_receipt, normalize_phone
    from orders.views.public_views import make_public_bill_token

    phone_input = (body.get("phone") or "").strip()
    if phone_input:
        if not normalize_phone(phone_input):
            return JsonResponse({"error": "That doesn't look like a valid phone number."}, status=400)
        if phone_input != order.customer_phone:
            order.customer_phone = phone_input
            order.save(update_fields=["customer_phone"])
    elif not order.customer_phone:
        return JsonResponse({"error": "Enter a customer phone number first."}, status=400)

    token = make_public_bill_token(order.id)
    bill_url = request.build_absolute_uri(reverse("public-bill", args=[token]))

    if send_bill_receipt(order, bill_url):
        return JsonResponse({"success": True, "phone": order.customer_phone})
    return JsonResponse({"error": "Couldn't reach WhatsApp. Check the number and try again."}, status=502)
