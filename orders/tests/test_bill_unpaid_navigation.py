# orders/tests/test_bill_unpaid_navigation.py
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from accounts.models import User
from tenants.models import Tenant, Outlet
from menu.models import MenuCategory, MenuItem
from orders.models import Order, OrderItem, Table
from setup.models import PaymentConfig


class BillUnpaidNavigationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Bill Navigation Test Tenant",
            tenant_type="fine_dining",
        )
        self.outlet = Outlet.objects.create(
            tenant=self.tenant,
            name="Main Outlet",
        )
        PaymentConfig.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            cash_enabled=True,
            upi_enabled=True,
        )
        self.owner = User.objects.create_user(
            username="owner_user",
            password="password123",
            tenant=self.tenant,
            outlet=self.outlet,
            role="owner",
        )
        self.cashier = User.objects.create_user(
            username="cashier_user",
            password="password123",
            tenant=self.tenant,
            outlet=self.outlet,
            role="cashier",
        )
        self.table = Table.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            name="T-1",
            state="free",
        )
        self.category = MenuCategory.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            name="Food",
        )
        self.menu_item = MenuItem.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            category=self.category,
            name="Paneer Butter Masala",
            price=Decimal("250.00"),
            is_available=True,
        )
        self.order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            table=self.table,
            created_by=self.owner,
            status="open",
            subtotal=Decimal("250.00"),
            grand_total=Decimal("250.00"),
        )
        OrderItem.objects.create(
            order=self.order,
            menu_item=self.menu_item,
            quantity=1,
            price=Decimal("250.00"),
            gst_percentage=5,
            total_price=Decimal("250.00"),
            status="served",
        )

    def test_owner_viewing_bill_does_not_close_or_pay_order(self):
        self.client.force_login(self.owner)
        
        # Owner clicks 'Bill' (triggers generate-bill)
        resp = self.client.post(reverse("generate-bill", args=[self.order.id]))
        self.assertEqual(resp.status_code, 200)
        
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "billing")
        
        # Owner views the bill details
        bill_resp = self.client.get(reverse("bill-view", args=[self.order.id]))
        self.assertEqual(bill_resp.status_code, 200)
        self.assertContains(bill_resp, "Paneer Butter Masala")
        # Ensure the safe back navigation is rendered, not the bypass link
        self.assertContains(bill_resp, "Back to Tables")
        self.assertNotContains(bill_resp, "Dashboard (Bypass)")
        
        # Order and table must still be active and NOT paid or closed
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "billing")
        self.assertEqual(self.order.payments.count(), 0)
        
        # Check tables_data returns table with is_paid = False
        tables_resp = self.client.get(reverse("tables-data"))
        self.assertEqual(tables_resp.status_code, 200)
        t_data = tables_resp.json()["tables"]
        t1 = next(t for t in t_data if t["id"] == self.table.id)
        self.assertEqual(t1["status"], "billing")
        self.assertFalse(t1["order"]["is_paid"])

    def test_generate_bill_idempotent_when_already_in_billing_status(self):
        self.client.force_login(self.owner)
        self.order.status = "billing"
        self.order.save(update_fields=["status"])
        
        # Calling generate-bill again should succeed and not return 404
        resp = self.client.post(reverse("generate-bill", args=[self.order.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    def test_explicit_admin_bypass_requires_owner_manager(self):
        self.client.force_login(self.cashier)
        resp = self.client.post(reverse("log-bypass", args=[self.order.id]))
        self.assertEqual(resp.status_code, 403)
        
        self.client.force_login(self.owner)
        resp = self.client.post(reverse("log-bypass", args=[self.order.id]))
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "closed")
