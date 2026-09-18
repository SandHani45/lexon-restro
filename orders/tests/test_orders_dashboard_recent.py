# orders/tests/test_orders_dashboard_recent.py
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from tenants.models import Tenant, Outlet
from menu.models import MenuCategory, MenuItem
from orders.models import Order, OrderItem, Table, Payment


class OrdersDashboardRecentOrdersTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Recent Orders Test Tenant",
            tenant_type="fine_dining",
        )
        self.outlet = Outlet.objects.create(
            tenant=self.tenant,
            name="Main Outlet",
        )
        self.owner = User.objects.create_user(
            username="owner_user",
            password="password123",
            tenant=self.tenant,
            outlet=self.outlet,
            role="owner",
        )
        self.table1 = Table.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            name="T-1",
            state="occupied",
        )
        self.table2 = Table.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            name="T-2",
            state="free",
        )
        self.category = MenuCategory.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            name="Food",
        )
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            category=self.category,
            name="Chicken Biryani",
            price=Decimal("250.00"),
            is_available=True,
        )

        self.client = Client()
        self.client.login(username="owner_user", password="password123")

    def test_active_orders_separate_from_recent_completed(self):
        """Active orders (open, billing) stay in active feed; completed orders (paid, closed) appear in recent_orders."""
        # 1. Create an active open order
        open_order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            table=self.table1,
            created_by=self.owner,
            source="dine_in",
            status="open",
            subtotal=Decimal("250.00"),
            gst_total=Decimal("12.50"),
            grand_total=Decimal("262.50"),
        )
        OrderItem.objects.create(
            order=open_order,
            menu_item=self.item,
            quantity=1,
            price=Decimal("250.00"),
            total_price=Decimal("250.00"),
            gst_percentage=Decimal("5.00"),
            status="pending",
        )

        # 2. Create an active billing order
        billing_order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            table=self.table2,
            created_by=self.owner,
            source="dine_in",
            status="billing",
            subtotal=Decimal("500.00"),
            gst_total=Decimal("25.00"),
            grand_total=Decimal("525.00"),
        )

        # 3. Create 6 paid/closed orders (only top 5 should be returned in recent_orders)
        completed_orders = []
        for i in range(6):
            o = Order.objects.create(
                tenant=self.tenant,
                outlet=self.outlet,
                created_by=self.owner,
                source="takeaway",
                status="paid",
                subtotal=Decimal(100 + i * 10),
                gst_total=Decimal(5),
                grand_total=Decimal(105 + i * 10),
                closed_at=timezone.now() + timezone.timedelta(minutes=i),
            )
            Payment.objects.create(
                order=o,
                amount=o.grand_total,
                method="upi" if i % 2 == 0 else "cash",
            )
            completed_orders.append(o)

        # Fetch /orders/data/ feed
        resp = self.client.get(reverse("orders-feed-data"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Verify active orders: should only have 2 (open_order and billing_order)
        active_ids = [o["id"] for o in data["orders"]]
        self.assertEqual(len(active_ids), 2)
        self.assertIn(open_order.id, active_ids)
        self.assertIn(billing_order.id, active_ids)
        for comp in completed_orders:
            self.assertNotIn(comp.id, active_ids)

        # Verify metrics
        self.assertEqual(data["metrics"]["active_orders"], 2)

        # Verify recent_orders: top 5 completed orders
        recent = data["recent_orders"]
        self.assertEqual(len(recent), 5)
        recent_ids = [o["id"] for o in recent]
        # Most recently closed order (index 5) should be first
        self.assertEqual(recent_ids[0], completed_orders[5].id)
        # Oldest of the 6 (index 0) was truncated by the [:5] limit
        self.assertNotIn(completed_orders[0].id, recent_ids)

        # Verify payment method serialization
        self.assertEqual(recent[0]["payment_method"], "CASH")
        self.assertTrue(recent[0]["is_paid"])

    def test_accept_order_with_prep_time(self):
        """Accepting an order with custom prep time saves prep_time_minutes, sends items to kitchen, and transitions category to accepted."""
        import json
        order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            table=self.table1,
            created_by=self.owner,
            source="web",  # QR code order
            status="open",
            subtotal=Decimal("250.00"),
            gst_total=Decimal("12.50"),
            grand_total=Decimal("262.50"),
        )
        item = OrderItem.objects.create(
            order=order,
            menu_item=self.item,
            quantity=1,
            price=Decimal("250.00"),
            total_price=Decimal("250.00"),
            gst_percentage=Decimal("5.00"),
            status="review",  # QR guest item
        )

        # Before accepting: feed reports category 'new'
        resp = self.client.get(reverse("orders-feed-data"))
        self.assertEqual(resp.status_code, 200)
        orders_data = resp.json()["orders"]
        target = next(o for o in orders_data if o["id"] == order.id)
        self.assertEqual(target["category"], "new")

        # Accept order with 25 minutes prep time
        accept_resp = self.client.post(
            reverse("accept-order", args=[order.id]),
            data=json.dumps({"prep_time": 25}),
            content_type="application/json"
        )
        self.assertEqual(accept_resp.status_code, 200)
        self.assertTrue(accept_resp.json()["success"])
        self.assertEqual(accept_resp.json()["prep_time_minutes"], 25)

        # Verify DB changes
        order.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(order.prep_time_minutes, 25)
        self.assertIsNotNone(order.estimated_ready_at)
        self.assertEqual(item.status, "sent")

        # Feed reports category 'accepted' with prep_time_minutes=25
        resp2 = self.client.get(reverse("orders-feed-data"))
        orders_data2 = resp2.json()["orders"]
        target2 = next(o for o in orders_data2 if o["id"] == order.id)
        self.assertEqual(target2["category"], "accepted")
        self.assertEqual(target2["prep_time_minutes"], 25)

    def test_serve_order(self):
        """Marking an order served marks items as served and transitions category to served."""
        order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            table=self.table1,
            created_by=self.owner,
            source="dine_in",
            status="open",
            subtotal=Decimal("250.00"),
            gst_total=Decimal("12.50"),
            grand_total=Decimal("262.50"),
        )
        OrderItem.objects.create(
            order=order,
            menu_item=self.item,
            quantity=1,
            price=Decimal("250.00"),
            total_price=Decimal("250.00"),
            gst_percentage=Decimal("5.00"),
            status="ready",
        )

        resp = self.client.post(reverse("serve-order", args=[order.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

        # Feed reports category 'served'
        resp2 = self.client.get(reverse("orders-feed-data"))
        orders_data2 = resp2.json()["orders"]
        target = next(o for o in orders_data2 if o["id"] == order.id)
        self.assertEqual(target["category"], "served")

