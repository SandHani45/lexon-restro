# webstore/views.py
"""
Browser-based ordering with no QR code: a customer visits
/<tenant-slug>/, logs in (or registers) with webstore.CustomerAccount --
a session identity kept fully separate from accounts.User/request.user,
see webstore/auth.py -- and orders for delivery. Table is always None
here (already a well-supported state throughout kitchen/billing/status
polling); item creation reuses the exact same order_service functions
the QR flow uses, with user=None passed through (identical code path to
an anonymous QR guest from order_service's point of view).

Feature-gated behind has_feature(tenant, "web_ordering"), which is
custom-only (off for every tenant by default) -- see core/features.py.
"""
import json
import logging

from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password, check_password
from django.http import JsonResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from core.features import has_feature
from core.validators import normalize_phone
from tenants.models import Tenant, Outlet
from menu.models import MenuCategory
from menu.views.customer_views import _build_modifier_data, _build_carousel_items
from orders.exceptions import OrderError, CartError, MenuItemError, ModifierError
from orders.models import Order
from orders.services.order_service import add_items_to_order
from orders.views.public_views import make_order_status_token

from .models import CustomerAccount
from .auth import login_customer, logout_customer, get_current_customer

logger = logging.getLogger("pos.webstore")


def _resolve_storefront(tenant_slug):
    """Tenant + its first/primary outlet for a web_ordering-enabled tenant, or 404."""
    tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
    if not has_feature(tenant, "web_ordering"):
        raise Http404
    outlet = Outlet.objects.filter(tenant=tenant, is_active=True).order_by("outlet_number").first()
    if not outlet:
        raise Http404
    return tenant, outlet


def store_home(request, tenant_slug):
    tenant, outlet = _resolve_storefront(tenant_slug)
    customer = get_current_customer(request)
    if not customer:
        return redirect("webstore_login", tenant_slug=tenant_slug)

    categories = list(
        MenuCategory.objects
        .filter(tenant=tenant, outlet=outlet, is_active=True)
        .prefetch_related("items", "items__modifier_groups__modifier_group__modifiers")
    )
    return render(request, "webstore/store.html", {
        "tenant": tenant,
        "outlet": outlet,
        "customer": customer,
        "categories": categories,
        "item_modifier_data": _build_modifier_data(categories),
        "carousel_items": _build_carousel_items(categories),
    })


@ratelimit(key="ip", rate="20/m", method="POST", block=False)
def customer_register(request, tenant_slug):
    tenant, _outlet = _resolve_storefront(tenant_slug)
    if getattr(request, "limited", False):
        return render(request, "webstore/register.html", {
            "tenant": tenant, "error": "Too many attempts. Please wait a moment."
        }, status=429)

    if get_current_customer(request):
        return redirect("webstore_home", tenant_slug=tenant_slug)

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        name = (request.POST.get("name") or "").strip()
        phone_raw = request.POST.get("phone") or ""

        error = None
        phone = None
        if not username or not password or not name:
            error = "Username, password, and name are required."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif CustomerAccount.objects.filter(username__iexact=username).exists():
            error = "That username is already taken."
        else:
            try:
                phone = normalize_phone(phone_raw) if phone_raw else None
            except ValidationError:
                error = "Enter a valid 10-digit phone number, or leave it blank."

        if error:
            return render(request, "webstore/register.html", {
                "tenant": tenant, "error": error,
                "username": username, "name": name, "phone": phone_raw,
            })

        customer = CustomerAccount.objects.create(
            username=username,
            password_hash=make_password(password),
            name=name,
            phone=phone or "",
        )
        login_customer(request, customer)
        return redirect("webstore_home", tenant_slug=tenant_slug)

    return render(request, "webstore/register.html", {"tenant": tenant})


@ratelimit(key="ip", rate="20/m", method="POST", block=False)
def customer_login(request, tenant_slug):
    tenant, _outlet = _resolve_storefront(tenant_slug)
    if getattr(request, "limited", False):
        return render(request, "webstore/login.html", {
            "tenant": tenant, "error": "Too many attempts. Please wait a moment."
        }, status=429)

    if get_current_customer(request):
        return redirect("webstore_home", tenant_slug=tenant_slug)

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        customer = CustomerAccount.objects.filter(username__iexact=username).first()
        if customer and check_password(password, customer.password_hash):
            login_customer(request, customer)
            return redirect("webstore_home", tenant_slug=tenant_slug)
        return render(request, "webstore/login.html", {
            "tenant": tenant, "error": "Incorrect username or password.", "username": username,
        })

    return render(request, "webstore/login.html", {"tenant": tenant})


def customer_logout(request, tenant_slug):
    logout_customer(request)
    return redirect("webstore_login", tenant_slug=tenant_slug)


@ratelimit(key="ip", rate="20/m", method="POST", block=False)
@require_POST
def create_web_order(request, tenant_slug):
    tenant, outlet = _resolve_storefront(tenant_slug)
    if getattr(request, "limited", False):
        return JsonResponse({"error": "Too many requests. Please wait a moment."}, status=429)

    customer = get_current_customer(request)
    if not customer:
        return JsonResponse({"error": "Please log in to place an order."}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "Invalid request."}, status=400)

    name = (data.get("customer_name") or customer.name or "").strip()
    address = (data.get("delivery_address") or "").strip()
    try:
        phone = normalize_phone(data.get("customer_phone") or customer.phone)
    except ValidationError:
        phone = None

    if not name:
        return JsonResponse({"error": "Please enter your name."}, status=400)
    if not phone:
        return JsonResponse({"error": "Enter a valid 10-digit phone number."}, status=400)
    if not address:
        return JsonResponse({"error": "Please enter a delivery address."}, status=400)

    cart = data.get("cart") or []
    if not cart:
        return JsonResponse({"error": "Your cart is empty."}, status=400)

    notes = (data.get("notes") or "").strip()

    # Order has no notes field of its own (only OrderItem does) -- fold the
    # delivery address into the first cart item's note instead, since
    # kitchen_service.py already surfaces OrderItem.notes on the KOT ticket
    # today. This makes the address visible to staff with zero template
    # changes anywhere outside this new app.
    address_note = f"Delivery Address: {address}" + (f" | {notes}" if notes else "")
    first_item = dict(cart[0])
    first_item["note"] = (address_note + (f" | {first_item['note']}" if first_item.get("note") else ""))
    cart = [first_item] + [dict(i) for i in cart[1:]]

    try:
        # No table (this is a browser/delivery order, not dine-in), and
        # unlike the table case there's no unique-open-order constraint to
        # merge onto for table=None -- multiple tableless orders (this
        # customer's, other customers', walk-ins) can be open at once for
        # the same outlet. So this always creates a fresh Order, exactly
        # matching orders.views.billing_views.create_order's own
        # `elif table is None: Order.objects.create(...)` branch -- calling
        # get_or_create_open_order here instead would raise
        # MultipleObjectsReturned as soon as a second tableless order was
        # already open.
        order = Order.objects.create(
            tenant=tenant,
            outlet=outlet,
            table=None,
            created_by=None,
            status="open",
            source="delivery",
            customer_name=name,
            customer_phone=phone,
            delivery_address=address,
        )
        add_items_to_order(None, order, cart, tenant=tenant, outlet=outlet)

        logger.info(
            "Webstore customer %s created order #%s for tenant %s (delivery)",
            customer.username, order.id, tenant.slug,
        )
        return JsonResponse({
            "success": True,
            "order_id": order.id,
            "status_token": make_order_status_token(order.id),
        })
    except (OrderError, CartError, MenuItemError, ModifierError):
        # Same posture as orders.views.billing_views.create_order: never
        # leak internal exception text to an unauthenticated-to-staff client.
        logger.exception("Webstore order creation failed (validation)")
        return JsonResponse({"error": "Could not create the order. Please try again."}, status=400)
    except Exception:
        logger.exception("Webstore order creation failed")
        return JsonResponse({"error": "Could not create the order. Please try again."}, status=500)
