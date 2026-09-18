# orders/views/table_views.py
import logging
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
import json

from core.decorators import tenant_required, role_required, feature_required
from orders.models import Order, OrderEvent, Table, FloorSection
from tablemerge.models import TableMerge

logger = logging.getLogger("pos.orders")


@login_required
@tenant_required
@feature_required("floor_plan")
def table_dashboard(request):
    return render(request, "orders/tables.html")


@login_required
@tenant_required
@feature_required("floor_plan")
def tables_data(request):
    try:
        tenant = request.user.tenant
        outlet = request.user.outlet
        now = timezone.now()

        tables = list(Table.objects.filter(tenant=tenant, outlet=outlet, is_active=True).order_by("name"))
        table_name_lookup = {t.id: t.name for t in tables}

        merges = (
            TableMerge.objects
            .filter(tenant=tenant, outlet=outlet, is_active=True)
            .select_related("primary_table")
            .prefetch_related("tables")
        )
        merged_lookup = {}
        primary_lookup = {}
        for merge in merges:
            primary_id = merge.primary_table.id
            primary_name = merge.primary_table.name
            primary_lookup[primary_id] = [t.name for t in merge.tables.all() if t.id != primary_id]
            for t in merge.tables.all():
                if t.id != primary_id:
                    merged_lookup[t.id] = (primary_id, primary_name)

        orders = (
            Order.objects
            .filter(tenant=tenant, outlet=outlet, status__in=["open", "billing"])
            .select_related("table", "created_by")
            .prefetch_related("items__menu_item", "payments")
        )
        orders_map = {o.table_id: o for o in orders}

        data = []
        for table in tables:
            try:
                merge_info = merged_lookup.get(table.id)
                is_secondary = bool(merge_info)
                primary_table_id = merge_info[0] if merge_info else None
                primary_table_name = merge_info[1] if merge_info else None
                
                is_primary = table.id in primary_lookup
                merged_with_names = primary_lookup.get(table.id, [])

                lookup_table_id = primary_table_id if primary_table_id else table.id
                order = orders_map.get(lookup_table_id)

                cooking_items = 0
                elapsed_minutes = 0
                order_summary = None
                if order:
                    cooking_items = sum(1 for i in order.items.all() if i.status in ["sent", "preparing"])
                    elapsed_minutes = int((now - order.created_at).total_seconds() / 60)
                    
                    order_items = []
                    for i in order.items.all():
                        if i.status != "voided":
                            order_items.append({
                                "id": i.id,
                                "name": i.menu_item.name if i.menu_item else "Item",
                                "quantity": i.quantity,
                                "price": float(i.price or 0),
                                "total_price": float(i.total_price or 0),
                                "status": i.status,
                            })
                    order_summary = {
                        "id": order.id,
                        "order_number": order.order_number or f"#{order.id}",
                        "short_id": (order.order_number.split("-")[-1] if order.order_number else str(order.id).zfill(4)),
                        "time": timezone.localtime(order.created_at).strftime("%I:%M %p"),
                        "subtotal": float(order.subtotal or 0),
                        "gst_total": float(order.gst_total or 0),
                        "grand_total": float(order.grand_total or 0),
                        "status": order.status,
                        "is_paid": bool((sum(p.amount for p in order.payments.all() if p.method != "refund") >= order.grand_total and order.grand_total > 0) or order.status == "paid"),
                        "items": order_items,
                    }

                if is_secondary:
                    status = "merged"
                elif table.state == "cleaning":
                    status = "cleaning"
                elif not order:
                    if table.state == "ordering":
                        # A seated reservation nudges the table here before
                        # any Order exists (crm's update_reservation_status) --
                        # the only non-"free" state that's legitimate with no
                        # order behind it.
                        status = "ordering"
                    elif table.state == "free":
                        status = "free"
                    else:
                        table.state = "free"
                        table.save(update_fields=["state"])
                        status = "free"
                elif order.status == "billing" or table.state == "billing":
                    status = "billing"
                else:
                    # Convert to list to use prefetch cache. Voided items are
                    # excluded — they're inert and must never keep a table
                    # looking active (same fix as update_table_state).
                    items_list = [i for i in order.items.all() if i.status != "voided"]

                    if not items_list:
                        status = "free"
                    elif any(i.status == "review" for i in items_list):
                        status = "needs_approval"
                    elif any(i.status == "pending" for i in items_list):
                        status = "ordering"
                    elif any(i.status in ["sent", "preparing"] for i in items_list):
                        status = "preparing"
                    elif any(i.status == "ready" for i in items_list):
                        status = "ready"
                    elif any(i.status == "served" for i in items_list):
                        status = "served"
                    else:
                        status = "ordering"

                data.append({
                    "id": table.id,
                    "name": table.name,
                    "section": table.section,
                    "capacity": table.capacity,
                    "shape": table.shape,
                    "pos_x": table.pos_x,
                    "pos_y": table.pos_y,
                    "width": table.width,
                    "height": table.height,
                    "qr_token": str(table.qr_token),
                    "status": status,
                    "order_id": order.id if order else None,
                    "cooking_items": cooking_items,
                    "elapsed": elapsed_minutes,
                    "elapsed_seconds": int((now - order.created_at).total_seconds()) if order else 0,
                    "order_created_at": order.created_at.isoformat() if order else None,
                    "merged": is_secondary or is_primary,
                    "is_primary": is_primary,
                    "merged_with_names": ", ".join(merged_with_names),
                    "primary_table": primary_table_id,
                    "primary_table_name": primary_table_name,
                    "waiter_name": (order.created_by.get_full_name() or order.created_by.username) if order and order.created_by else ("Guest (QR)" if order else ""),
                    "waiter_initials": "".join([n[0] for n in (order.created_by.get_full_name() or order.created_by.username).split()])[:2].upper() if order and order.created_by else ("QR" if order else ""),
                    "order": order_summary,
                })
            except Exception as e:
                data.append({"id": table.id, "name": table.name, "section": table.section, "status": "error",
                             "capacity": getattr(table, "capacity", 4), "shape": getattr(table, "shape", "square"),
                             "pos_x": getattr(table, "pos_x", None), "pos_y": getattr(table, "pos_y", None),
                             "width": getattr(table, "width", None), "height": getattr(table, "height", None),
                             "order_id": None, "cooking_items": 0, "elapsed": 0, "elapsed_seconds": 0, "order_created_at": None, "order": None,
                             "merged": False, "primary_table": None, "primary_table_name": None})

        sections = list(FloorSection.objects.filter(
            tenant=tenant, outlet=outlet
        ).values("id", "name", "width", "height", "grid_size"))
        return JsonResponse({"tables": data, "sections": sections})

    except Exception:
        logger.exception("tables_data failed")
        return JsonResponse({"error": "tables_data_failed", "message": "Could not load table data. Please try again."}, status=500)


@login_required
@require_POST
@tenant_required
@feature_required("floor_plan")
def mark_table_cleaned(request, table_id):
    try:
        table = Table.objects.get(id=table_id, tenant=request.user.tenant, outlet=request.user.outlet)
        table.state = "free"
        table.save(update_fields=["state"])
        logger.info("User %s marked table %s as cleaned", request.user.username, table.name)
        return JsonResponse({"success": True})
    except Table.DoesNotExist:
        return JsonResponse({"error": "Table not found"}, status=404)


@login_required
@tenant_required
@feature_required("floor_plan")
def available_tables(request):
    tenant = request.user.tenant
    outlet = request.user.outlet
    active_table_ids = set(
        Order.objects.filter(tenant=tenant, outlet=outlet, status__in=["open", "billing"])
        .values_list("table_id", flat=True)
    )
    merged_table_ids = set(
        TableMerge.objects.filter(tenant=tenant, outlet=outlet, is_active=True)
        .values_list("tables__id", flat=True)
    )
    tables = (
        Table.objects.filter(tenant=tenant, outlet=outlet, is_active=True)
        .exclude(id__in=active_table_ids)
        .exclude(id__in=merged_table_ids)
        .values("id", "name")
    )
    return JsonResponse({"tables": list(tables)})


# merge_tables_view/unmerge_tables_view moved to tablemerge/views.py
# (Phase 5 of the orders app split) -- TableMerge is still imported above
# because tables_data/available_tables/transfer_table_view below all read
# it directly.


@login_required
@tenant_required
@feature_required("floor_plan")
@require_POST
def transfer_table_view(request):
    try:
        data = json.loads(request.body)
        order_id = data.get("order_id")
        table_id = data.get("table_id")

        if not order_id or not table_id:
            return JsonResponse({"error": "Missing parameters"}, status=400)
        try:
            order_id = int(order_id)
            table_id = int(table_id)
        except (ValueError, TypeError):
            return JsonResponse({"error": "Invalid IDs"}, status=400)

        tenant = request.user.tenant
        outlet = request.user.outlet

        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .filter(id=order_id, tenant=tenant, outlet=outlet).first()
            )
            if not order:
                return JsonResponse({"error": "Order not found"}, status=404)
            if order.status in ["billing", "paid", "closed"]:
                return JsonResponse({"error": "Cannot transfer at this stage"}, status=400)

            new_table = Table.objects.filter(id=table_id, tenant=tenant, outlet=outlet, is_active=True).first()
            if not new_table:
                return JsonResponse({"error": "Invalid table"}, status=400)
            if new_table.id == order.table_id:
                return JsonResponse({"error": "Same table"}, status=400)

            if TableMerge.objects.filter(tenant=tenant, outlet=outlet, is_active=True, tables=new_table).exists():
                return JsonResponse({"error": "Cannot transfer to merged table"}, status=400)

            if Order.objects.filter(tenant=tenant, outlet=outlet, table=new_table, status__in=["open", "billing"]).exists():
                return JsonResponse({"error": "Table already occupied"}, status=400)

            old_table = order.table
            order.table = new_table
            order.save(update_fields=["table"])

            if old_table:
                old_table.state = "free"
                old_table.save(update_fields=["state"])
            new_table.state = "ordering"
            new_table.save(update_fields=["state"])

            OrderEvent.objects.create(
                tenant=tenant, outlet=outlet, order=order,
                event_type="table_transferred",
                metadata={"from_table_id": old_table.id if old_table else None, "to_table_id": new_table.id},
                created_by=request.user
            )
            logger.info(
                "User %s transferred order #%s from %s to %s",
                request.user.username, order.id,
                old_table.name if old_table else '?', new_table.name,
            )

        return JsonResponse({"success": True, "order_id": order.id})

    except Exception:
        logger.exception("Error transferring table")
        return JsonResponse({"error": "Could not transfer the table. Please try again."}, status=400)


@login_required
@tenant_required
@feature_required("floor_plan")
@role_required("manager", "owner")
@require_POST
def manage_table_view(request):
    try:
        data = json.loads(request.body)
        table_id = data.get("table_id")
        action = data.get("action")
        
        tenant = request.user.tenant
        outlet = request.user.outlet
        
        if action == "create":
            name = data.get("name")
            if not name:
                return JsonResponse({"error": "Table name is required"}, status=400)
            section = data.get("section", "Main Hall")
            capacity = int(data.get("capacity", 4))
            shape = data.get("shape", "square")
            pos_x = data.get("pos_x")
            pos_y = data.get("pos_y")
            width = data.get("width")
            height = data.get("height")
            tbl = Table.objects.create(
                name=name,
                section=section,
                capacity=capacity,
                shape=shape,
                pos_x=pos_x,
                pos_y=pos_y,
                width=width,
                height=height,
                tenant=tenant,
                outlet=outlet
            )
            return JsonResponse({"success": True, "table_id": tbl.id})
            
        table = Table.objects.get(id=table_id, tenant=tenant, outlet=outlet)
        
        if action == "edit":
            name = data.get("name")
            section = data.get("section")
            capacity = data.get("capacity")
            shape = data.get("shape")
            pos_x = data.get("pos_x")
            pos_y = data.get("pos_y")
            width = data.get("width")
            height = data.get("height")
            if name is not None: table.name = name
            if section is not None: table.section = section
            if capacity is not None: table.capacity = int(capacity)
            if shape is not None: table.shape = shape
            if pos_x is not None or "pos_x" in data: table.pos_x = pos_x
            if pos_y is not None or "pos_y" in data: table.pos_y = pos_y
            if width is not None or "width" in data: table.width = width
            if height is not None or "height" in data: table.height = height
            table.save()
            return JsonResponse({"success": True})

        if action == "delete":
            if Order.objects.filter(tenant=tenant, outlet=outlet, table=table, status__in=["open", "billing"]).exists():
                return JsonResponse({"error": "Cannot delete a table with an active order"}, status=400)
            table.is_active = False
            table.save(update_fields=["is_active"])
            return JsonResponse({"success": True})

        return JsonResponse({"error": f"Unknown action: {action}"}, status=400)

    except Table.DoesNotExist:
        return JsonResponse({"error": "Table not found"}, status=404)
    except Exception:
        logger.exception("Error managing table")
        return JsonResponse({"error": "Could not complete that action. Please try again."}, status=400)


@login_required
@tenant_required
@feature_required("floor_plan")
@role_required("manager", "owner")
def floor_editor_view(request):
    return render(request, "orders/floor_editor.html")


@login_required
@tenant_required
@feature_required("floor_plan")
@role_required("manager", "owner")
def floor_data_api(request):
    try:
        tenant = request.user.tenant
        outlet = request.user.outlet

        # Get all distinct sections from FloorSection models + existing tables
        db_sections = FloorSection.objects.filter(tenant=tenant, outlet=outlet)
        section_map = {s.name: {"name": s.name, "width": s.width, "height": s.height, "grid_size": s.grid_size} for s in db_sections}

        table_sections = Table.objects.filter(tenant=tenant, outlet=outlet, is_active=True).values_list("section", flat=True).distinct()
        for sec in table_sections:
            sec_name = sec.strip() if sec else "Main Hall"
            if not sec_name:
                sec_name = "Main Hall"
            if sec_name not in section_map:
                section_map[sec_name] = {"name": sec_name, "width": 900, "height": 500, "grid_size": 40}

        if not section_map:
            section_map["Main Hall"] = {"name": "Main Hall", "width": 900, "height": 500, "grid_size": 40}

        tables = Table.objects.filter(tenant=tenant, outlet=outlet, is_active=True).order_by("name")
        tables_list = []
        for t in tables:
            tables_list.append({
                "id": t.id,
                "name": t.name,
                "section": t.section or "Main Hall",
                "capacity": t.capacity,
                "shape": t.shape or "square",
                "pos_x": t.pos_x,
                "pos_y": t.pos_y,
                "width": t.width,
                "height": t.height,
                "qr_token": str(t.qr_token),
                "state": t.state,
            })

        return JsonResponse({
            "sections": list(section_map.values()),
            "tables": tables_list
        })
    except Exception:
        logger.exception("floor_data_api failed")
        return JsonResponse({"error": "Failed to load floor editor data"}, status=500)


@login_required
@tenant_required
@feature_required("floor_plan")
@role_required("manager", "owner")
@require_POST
def save_floor_layout(request):
    try:
        data = json.loads(request.body)
        tenant = request.user.tenant
        outlet = request.user.outlet

        section_name = data.get("section", "Main Hall").strip()
        if not section_name:
            section_name = "Main Hall"

        width = int(data.get("width", 900))
        height = int(data.get("height", 500))
        grid_size = int(data.get("grid_size", 40))

        # Update or create floor section dimensions
        FloorSection.objects.update_or_create(
            tenant=tenant,
            outlet=outlet,
            name=section_name,
            defaults={"width": width, "height": height, "grid_size": grid_size}
        )

        tables_data = data.get("tables", [])
        saved_tables = []
        with transaction.atomic():
            for t_data in tables_data:
                t_id = t_data.get("id")
                name = str(t_data.get("name", "")).strip()
                capacity = int(t_data.get("capacity", 4))
                shape = t_data.get("shape", "square")
                pos_x = t_data.get("pos_x")
                pos_y = t_data.get("pos_y")
                t_width = t_data.get("width")
                t_height = t_data.get("height")
                sec = str(t_data.get("section", section_name)).strip() or section_name

                if t_id and not str(t_id).startswith("temp_"):
                    # Existing table
                    table = Table.objects.filter(id=t_id, tenant=tenant, outlet=outlet).first()
                    if table:
                        if name: table.name = name
                        table.section = sec
                        table.capacity = capacity
                        table.shape = shape
                        table.pos_x = pos_x
                        table.pos_y = pos_y
                        table.width = t_width
                        table.height = t_height
                        table.save()
                        saved_tables.append({"id": table.id, "temp_id": None, "name": table.name})
                else:
                    # New table created in canvas
                    if not name:
                        name = f"T-{Table.objects.filter(tenant=tenant, outlet=outlet).count() + 1}"
                    new_table = Table.objects.create(
                        tenant=tenant,
                        outlet=outlet,
                        name=name,
                        section=sec,
                        capacity=capacity,
                        shape=shape,
                        pos_x=pos_x,
                        pos_y=pos_y,
                        width=t_width,
                        height=t_height,
                    )
                    saved_tables.append({"id": new_table.id, "temp_id": t_id, "name": new_table.name})

            # Delete items if requested
            deleted_ids = data.get("deleted_ids", [])
            for del_id in deleted_ids:
                if del_id and not str(del_id).startswith("temp_"):
                    Table.objects.filter(id=del_id, tenant=tenant, outlet=outlet).update(is_active=False)

        return JsonResponse({"success": True, "saved_tables": saved_tables})

    except Exception:
        logger.exception("save_floor_layout failed")
        return JsonResponse({"error": "Failed to save floor layout"}, status=500)


@login_required
@tenant_required
@feature_required("floor_plan")
def live_tables_view(request):
    tenant = request.user.tenant
    outlet = request.user.outlet
    sections = list(FloorSection.objects.filter(tenant=tenant, outlet=outlet).values_list("name", flat=True))
    table_sections = list(Table.objects.filter(tenant=tenant, outlet=outlet, is_active=True).values_list("section", flat=True).distinct())
    all_sections = sorted(list(set(filter(None, sections + table_sections))))
    if not all_sections:
        all_sections = ["Floor 1"]
        
    return render(request, "orders/live_tables.html", {
        "sections": all_sections,
    })


