# orders/views/order_views.py
import json
import logging
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Q

from django.db import transaction
from core.decorators import tenant_required, feature_required
from orders.models import Order, OrderItem, Table, FloorSection
from waiter.models import WaiterCall
from tablemerge.models import TableMerge
from orders.services.event_service import log_event

logger = logging.getLogger("pos.orders")


@login_required
@tenant_required
@feature_required("running_order")
def running_order_view(request, order_id):
    order = Order.objects.filter(
        id=order_id,
        tenant=request.user.tenant,
        outlet=request.user.outlet
    ).first()

    if not order:
        return JsonResponse({"error": "Order not found"}, status=404)

    return render(request, "orders/running_order.html", {"order": order})


@login_required
@tenant_required
def running_order_items(request):
    # Shared by two different screens for two different reasons: fine
    # dining's Running Order page (feature "running_order") and QSR/cafe's
    # Token Billing (feature "token_system", which is what actually needs
    # this data -- franchise/cafe tenants don't get "running_order" at
    # all by default). feature_required() only supports requiring ALL of
    # a list of features, not EITHER/OR, so this is checked inline instead
    # -- gating on "running_order" alone left Token Billing's own item list
    # silently 403ing (rendered as an unparseable HTML 403 page, not JSON,
    # since this URL doesn't start with /api/) for any cafe/franchise
    # tenant without a manual feature override.
    from core.features import has_feature
    tenant = getattr(request.user, "tenant", None)
    if not request.user.is_superuser and not (
        has_feature(tenant, "running_order") or has_feature(tenant, "token_system")
    ):
        return JsonResponse(
            {"error": "This feature is not available for your account type."}, status=403
        )
    try:
        table_id = request.GET.get("table")
        order_id = request.GET.get("order")

        tenant = request.user.tenant
        outlet = request.user.outlet

        order = None

        # Filtering/ordering the items HERE, as part of the Prefetch
        # queryset, is what actually makes it get cached -- doing
        # order.items.exclude(...).order_by(...) later (as this used to)
        # builds a brand new, uncached queryset on the related manager
        # every time it's touched, silently throwing away the
        # prefetch_related above it and firing a fresh query per item for
        # menu_item and modifiers (classic N+1). This endpoint is polled
        # every 5s by every staff member with Token Billing open, so that
        # N+1 was real, recurring load on an already memory-constrained
        # server -- not just theoretical.
        from django.db.models import Prefetch
        _items_prefetch = Prefetch(
            "items",
            queryset=(
                OrderItem.objects
                .exclude(status="voided")
                .order_by("id")
                .select_related("menu_item")
                .prefetch_related("modifiers")
            ),
        )

        if order_id:
            try:
                order_id = int(order_id)
                order = (
                    Order.objects
                    .filter(id=order_id, tenant=tenant, outlet=outlet)
                    .prefetch_related(_items_prefetch)
                    .first()
                )
            except (ValueError, TypeError):
                pass
        elif table_id:
            try:
                table_id = int(table_id)
                # Resolve table merge
                merge = (
                    TableMerge.objects
                    .filter(
                        tenant=tenant, outlet=outlet,
                        is_active=True, tables__id=table_id
                    )
                    .select_related("primary_table")
                    .first()
                )
                if merge:
                    table_id = merge.primary_table.id

                order = (
                    Order.objects
                    .filter(
                        tenant=tenant, outlet=outlet,
                        table_id=table_id,
                        status__in=["open", "billing"]
                    )
                    .prefetch_related(_items_prefetch)
                    .order_by("-created_at")
                    .first()
                )
            except (ValueError, TypeError):
                pass

        if not order:
            return JsonResponse({"items": [], "order_id": None, "order_status": None})

        items = []
        for i in order.items.all():  # already filtered/ordered/prefetched via _items_prefetch above
            item_name = i.menu_item.name if i.menu_item else "Unknown Item"
            items.append({
                "id": i.id,
                "name": item_name,
                "quantity": i.quantity,
                "status": i.status,
                "price": float(i.price),
                "total": float(i.total_price),
                "modifiers": [m.name for m in i.modifiers.all()]
            })

        from django.db.models import Sum
        token = getattr(order, "token", None)
        total_paid = (
            order.payments.exclude(method="refund").aggregate(total=Sum("amount"))["total"]
            or 0
        )
        remaining = max(0, float(order.grand_total or 0) - float(total_paid))

        return JsonResponse({
            "items": items,
            "order_id": order.id,
            "order_status": order.status,
            "order_status_display": order.get_status_display(),
            "grand_total": float(order.grand_total or 0),
            "parcel_on": float(order.parcel_surcharge or 0) > 0,
            "parcel_amount": float(order.parcel_surcharge or 0),
            # Everything the Token Billing "Current Order" header/action area
            # needs to switch to a different order WITHOUT a full page reload
            # (see tokens/templates/tokens/token_billing.html::selectToken) --
            # a full navigation there used to re-render the whole menu grid,
            # popularity sort, and payment config just to show a different
            # order's items.
            "token_display": token.display_number if token else None,
            "remaining": remaining,
        })

    except Exception as e:
        logger.error("running_order_items error: %s", e)
        return JsonResponse({"items": [], "order_id": None})


@login_required
@tenant_required
@feature_required("running_order")
def running_order_data(request, order_id):
    order = (
        Order.objects
        .select_related("table")
        .prefetch_related("items__menu_item", "items__modifiers")
        .filter(
            id=order_id,
            tenant=request.user.tenant,
            outlet=request.user.outlet
        )
        .first()
    )

    if not order:
        return JsonResponse({"error": "Order not found"}, status=404)

    items = []
    for i in order.items.all():
        items.append({
            "id": i.id,
            "name": i.menu_item.name,
            "quantity": i.quantity,
            "status": i.status,
            "modifiers": [m.name for m in i.modifiers.all()]
        })

    return JsonResponse({
        "subtotal": float(order.subtotal),
        "gst": float(order.gst_total),
        "total": float(order.grand_total),
        "items": items
    })


@login_required
@tenant_required
@feature_required("qr_menu")
@require_POST
def approve_items(request, order_id):
    """Waiters approve items added via QR code."""
    try:
        tenant = request.user.tenant
        outlet = request.user.outlet
        
        with transaction.atomic():
            items = OrderItem.objects.filter(
                order_id=order_id,
                order__tenant=tenant,
                order__outlet=outlet,
                status="review"
            ).select_for_update()
            
            if not items.exists():
                return JsonResponse({"error": "No items found for approval"}, status=404)
            
            count = items.count()
            items.update(status="pending")
            
            order = Order.objects.get(id=order_id)
            
            # Trigger KOT creation for the newly approved items
            try:
                from kitchen.services.kot_service import create_kot
                create_kot(request.user, order)
            except Exception as kot_err:
                logger.error("KOT Creation failed during approval: %s", kot_err)
                # We don't fail the whole request, but we log it
            
            log_event(order, "status_changed", request.user, {"action": "items_approved", "count": count})
            
            logger.info("User %s approved %s items for order #%s", request.user.username, count, order_id)
            
        return JsonResponse({"success": True, "count": count})
    except Exception:
        logger.exception("approve_items error")
        return JsonResponse({"error": "Could not approve the items. Please try again."}, status=400)


@login_required
@tenant_required
@feature_required("qr_menu")
@require_POST
def approve_item(request, item_id):
    """
    Singular sibling of approve_items — lets staff approve one QR-guest
    item at a time instead of all-or-nothing, with cancel_item (existing,
    already "review"-safe — see void_service.void_order_item) as the
    per-item counterpart for rejecting instead of approving.

    Deliberately does NOT create a KOT (unlike approve_items, which does).
    approve_items is fine-dining's "waiter approves a QR add-on" action --
    dine-in customers eat before they pay, so kitchen prep starting the
    moment an item is approved is correct there. This one is used on
    Token Billing (QSR/cafe counter orders), which is the opposite model:
    pay first, then the kitchen fires -- see pay_order's _auto_kot, which
    now fires for every token order regardless of whether the outlet also
    runs a kitchen display. Approving here just accepts the item onto the
    bill; the KOT gets created once at payment, not once per approval.
    """
    try:
        with transaction.atomic():
            item = (
                OrderItem.objects
                .select_for_update()
                .select_related("order")
                .get(
                    id=item_id,
                    order__tenant=request.user.tenant,
                    order__outlet=request.user.outlet,
                )
            )
            if item.status != "review":
                return JsonResponse({"error": "Item is not awaiting approval"}, status=400)

            item.status = "pending"
            item.save(update_fields=["status"])

            order = item.order
            log_event(order, "status_changed", request.user, {"action": "item_approved", "item_id": item.id})
            logger.info("User %s approved item #%s", request.user.username, item_id)

        return JsonResponse({"success": True})
    except OrderItem.DoesNotExist:
        return JsonResponse({"error": "Item not found"}, status=404)
    except Exception:
        logger.exception("approve_item error")
        return JsonResponse({"error": "Could not approve the item. Please try again."}, status=400)


@login_required
@tenant_required
@require_POST
def accept_order_view(request, order_id):
    """
    Accept an order (from QR code, takeaway, table, etc.) with estimated prep time.
    1. Validates order belongs to user tenant/outlet.
    2. Parses prep_time (minutes, default 15) from request JSON.
    3. Saves prep_time_minutes and calculates estimated_ready_at.
    4. Approves any items in 'review' status -> 'pending'.
    5. Sends pending items to kitchen via create_kot() and marks them 'sent'.
    6. Logs event for auditing.
    """
    tenant = request.user.tenant
    outlet = request.user.outlet

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        data = {}

    try:
        prep_time_minutes = int(data.get("prep_time", 15))
        if prep_time_minutes <= 0 or prep_time_minutes > 300:
            prep_time_minutes = 15
    except (ValueError, TypeError):
        prep_time_minutes = 15

    try:
        with transaction.atomic():
            order = (
                Order.objects
                .select_for_update()
                .filter(id=order_id, tenant=tenant, outlet=outlet)
                .first()
            )
            if not order:
                return JsonResponse({"error": "Order not found"}, status=404)

            now = timezone.now()
            order.prep_time_minutes = prep_time_minutes
            order.estimated_ready_at = now + timezone.timedelta(minutes=prep_time_minutes)
            order.save(update_fields=["prep_time_minutes", "estimated_ready_at"])

            # 1. Update any review items (QR code guests) to pending
            review_items = OrderItem.objects.filter(
                order=order, status="review"
            ).select_for_update()
            if review_items.exists():
                review_items.update(status="pending")

            # 2. Send pending items to kitchen
            pending_items = OrderItem.objects.filter(
                order=order, status="pending"
            ).select_for_update()

            kot_created = False
            if pending_items.exists():
                try:
                    from kitchen.services.kot_service import create_kot
                    create_kot(request.user, order)
                    kot_created = True
                except Exception as kot_err:
                    logger.warning("KOT creation on accept order #%s: %s", order.id, kot_err)
                    pending_items.update(status="sent")

            # Update table state to busy if dine-in
            if order.table and order.table.state != "busy":
                order.table.state = "busy"
                order.table.save(update_fields=["state"])

            log_event(order, "status_changed", request.user, {
                "action": "order_accepted",
                "prep_time_minutes": prep_time_minutes,
                "kot_created": kot_created
            })

            logger.info("Order #%s accepted with %s min prep time by %s", order.id, prep_time_minutes, request.user.username)

        return JsonResponse({
            "success": True,
            "order_id": order.id,
            "prep_time_minutes": prep_time_minutes,
            "category": "accepted"
        })
    except Exception as e:
        logger.exception("accept_order_view error for order #%s", order_id)
        return JsonResponse({"error": "Could not accept order: " + str(e)}, status=400)


@login_required
@tenant_required
@require_POST
def serve_order_view(request, order_id):
    """Marks all non-voided items of an order as 'served'."""
    order = Order.objects.filter(id=order_id, tenant=request.user.tenant, outlet=request.user.outlet).first()
    if not order:
        return JsonResponse({"error": "Order not found"}, status=404)
    with transaction.atomic():
        order.items.exclude(status__in=["served", "voided"]).update(status="served")
        from orders.services.order_service import update_table_state
        update_table_state(order)
    return JsonResponse({"success": True})


@login_required
@tenant_required
def orders_page_view(request):
    """
    Main Orders Management dashboard matching modern POS design.
    """
    tenant = request.user.tenant
    outlet = request.user.outlet
    
    sections = list(FloorSection.objects.filter(tenant=tenant, outlet=outlet).values_list("name", flat=True))
    table_sections = list(Table.objects.filter(tenant=tenant, outlet=outlet, is_active=True).values_list("section", flat=True).distinct())
    all_sections = sorted(list(set(filter(None, sections + table_sections))))
    if not all_sections:
        all_sections = ["Floor 1"]

    return render(request, "orders/orders_dashboard.html", {
        "sections": all_sections,
    })


@login_required
@tenant_required
def orders_feed_data(request):
    """
    JSON feed providing live orders, metrics, service requests, and mini-map tables.
    """
    tenant = request.user.tenant
    outlet = request.user.outlet
    now = timezone.now()
    today_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)

    # 1. Metrics
    today_orders_qs = Order.objects.filter(tenant=tenant, outlet=outlet, created_at__gte=today_start)
    today_count = today_orders_qs.count()
    
    active_orders_qs = Order.objects.filter(
        tenant=tenant, outlet=outlet, status__in=["open", "billing"]
    ).select_related("table", "created_by").prefetch_related("items__menu_item")

    active_count = active_orders_qs.count()
    
    # 2. Service Requests (unresolved Waiter Calls)
    service_requests = []
    try:
        calls = WaiterCall.objects.filter(
            tenant=tenant, outlet=outlet, is_resolved=False
        ).select_related("table").order_by("-created_at")
        for c in calls:
            service_requests.append({
                "id": c.id,
                "table_id": c.table.id if c.table else None,
                "table_name": c.table.name if c.table else "Unknown",
                "reason": "Water / Assistance",
                "time": timezone.localtime(c.created_at).strftime("%I:%M %p"),
            })
    except Exception as e:
        logger.warning("Failed to fetch waiter calls: %s", e)

    # 3. Active Orders List (Currently live: open or billing)
    active_orders_qs = Order.objects.filter(
        tenant=tenant, outlet=outlet, status__in=["open", "billing"]
    ).select_related("table", "created_by").prefetch_related("items__menu_item", "payments").order_by("-created_at")

    orders_data = []
    served_count = 0

    for o in active_orders_qs:
        items_list = [i for i in o.items.all() if i.status != "voided"]
        
        # Determine order category
        category = "new"
        if o.status == "billing":
            category = "served"
            served_count += 1
        elif any(i.status == "review" for i in items_list):
            category = "new"
        elif any(i.status == "pending" for i in items_list) and not any(i.status in ["sent", "preparing", "ready", "served"] for i in items_list):
            category = "new"
        elif any(i.status == "sent" for i in items_list):
            category = "accepted"
        elif any(i.status == "preparing" for i in items_list):
            category = "preparing"
        elif any(i.status == "ready" for i in items_list):
            category = "ready"
        elif any(i.status == "served" for i in items_list):
            category = "served"
            served_count += 1
        else:
            category = "new"

        serialized_items = []
        for i in items_list:
            unit_price = float(i.price or 0)
            tot_price = float(i.total_price) if i.total_price is not None else round(unit_price * i.quantity, 2)
            serialized_items.append({
                "id": i.id,
                "name": i.menu_item.name if i.menu_item else "Item",
                "quantity": i.quantity,
                "price": unit_price,
                "total_price": tot_price,
                "status": i.status,
            })

        order_short_id = (o.order_number.split("-")[-1] if o.order_number else str(o.id).zfill(4))
        if o.table:
            tname = o.table.name.strip()
            display_name = tname if tname.lower().startswith("table") else f"Table {tname}"
        else:
            display_name = "Takeaway"

        orders_data.append({
            "id": o.id,
            "order_number": o.order_number or f"#{o.id}",
            "short_id": order_short_id,
            "table_id": o.table.id if o.table else None,
            "table_name": display_name,
            "time": timezone.localtime(o.created_at).strftime("%I:%M %p"),
            "category": category,
            "status": o.status,
            "is_paid": False,
            "prep_time_minutes": o.prep_time_minutes or 15,
            "subtotal": float(o.subtotal or 0),
            "gst_total": float(o.gst_total or 0),
            "grand_total": float(o.grand_total or 0),
            "created_at": o.created_at.isoformat(),
            "elapsed_seconds": int((now - o.created_at).total_seconds()),
            "items": serialized_items,
        })

    # 4. Recent Completed Orders (Top 5 most recently paid / closed)
    recent_completed_qs = Order.objects.filter(
        tenant=tenant, outlet=outlet, status__in=["paid", "closed"]
    ).select_related("table", "created_by").prefetch_related("items__menu_item", "payments").order_by("-closed_at", "-updated_at", "-created_at")[:5]

    recent_orders_data = []
    for o in recent_completed_qs:
        items_list = [i for i in o.items.all() if i.status != "voided"]
        serialized_items = []
        for i in items_list:
            unit_price = float(i.price or 0)
            tot_price = float(i.total_price) if i.total_price is not None else round(unit_price * i.quantity, 2)
            serialized_items.append({
                "id": i.id,
                "name": i.menu_item.name if i.menu_item else "Item",
                "quantity": i.quantity,
                "price": unit_price,
                "total_price": tot_price,
                "status": i.status,
            })

        order_short_id = (o.order_number.split("-")[-1] if o.order_number else str(o.id).zfill(4))
        if o.table:
            tname = o.table.name.strip()
            display_name = tname if tname.lower().startswith("table") else f"Table {tname}"
        else:
            display_name = "Takeaway"

        valid_payments = [p for p in o.payments.all() if p.method != "refund"]
        payment_method = valid_payments[0].method.upper() if valid_payments else "CASH"

        time_dt = o.closed_at or o.updated_at or o.created_at
        time_str = timezone.localtime(time_dt).strftime("%I:%M %p")

        recent_orders_data.append({
            "id": o.id,
            "order_number": o.order_number or f"#{o.id}",
            "short_id": order_short_id,
            "table_id": o.table.id if o.table else None,
            "table_name": display_name,
            "time": time_str,
            "category": "served",
            "status": o.status,
            "is_paid": True,
            "payment_method": payment_method,
            "subtotal": float(o.subtotal or 0),
            "gst_total": float(o.gst_total or 0),
            "grand_total": float(o.grand_total or 0),
            "created_at": o.created_at.isoformat(),
            "items": serialized_items,
        })

    # 4. Tables for the mini-map
    tables = Table.objects.filter(tenant=tenant, outlet=outlet, is_active=True).order_by("name")
    active_order_map = {o.table_id: o for o in active_orders_qs if o.table_id}

    tables_data_list = []
    for t in tables:
        t_order = active_order_map.get(t.id)
        is_busy = (t_order is not None or t.state not in ["free", "cleaning"])
        elapsed_sec = int((now - t_order.created_at).total_seconds()) if t_order else 0
        tables_data_list.append({
            "id": t.id,
            "name": t.name,
            "section": t.section or "Floor 1",
            "capacity": t.capacity or 4,
            "shape": t.shape or "square",
            "pos_x": t.pos_x,
            "pos_y": t.pos_y,
            "width": t.width,
            "height": t.height,
            "status": "busy" if is_busy else "free",
            "elapsed_seconds": elapsed_sec,
            "is_busy": is_busy,
            "order_id": t_order.id if t_order else None,
        })

    sections = list(FloorSection.objects.filter(tenant=tenant, outlet=outlet).values_list("name", flat=True))
    table_sections = list(tables.values_list("section", flat=True).distinct())
    all_sections = sorted(list(set(filter(None, sections + table_sections))))
    if not all_sections:
        all_sections = ["Floor 1"]

    return JsonResponse({
        "metrics": {
            "active_orders": len(orders_data),
            "served": served_count,
            "todays_orders": today_count,
        },
        "service_requests": service_requests,
        "orders": orders_data,
        "recent_orders": recent_orders_data,
        "tables": tables_data_list,
        "sections": all_sections,
    })

