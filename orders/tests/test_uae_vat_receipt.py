"""
UAE VAT Receipt — QA regression tests
=======================================

Covers the AE + gst_inclusive receipt wording added to:
  - orders/services/printing_service.py (_print_bill_body, ESC/POS)
  - orders/templates/orders/thermal_receipt.html (HTML print/preview path)
  - orders/models.py (Order.effective_vat_rate)

Run: python manage.py test orders.tests.test_uae_vat_receipt --keepdb
"""

import base64
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse

from accounts.models import User
from menu.models import MenuCategory, MenuItem
from orders.models import Order, OrderItem
from orders.services.printing_service import PrintingService
from printing.views import _build_receipt_b64
from setup.models import PaymentConfig
from tenants.models import Outlet, Tenant


class BP:
    """Minimal ESC/POS byte-capturing fake printer (mirrors test_printing_service.py)."""
    def __init__(self, encoding="cp437"):
        self.buf = b""
        self._enc = encoding

    def text(self, t):
        if isinstance(t, str):
            self.buf += t.encode(self._enc, errors="replace")
        else:
            self.buf += bytes(t)

    def set(self, **kw):
        pass

    def cut(self, mode="FULL"):
        pass


class UAEVatReceiptBase(TestCase):
    """Shared fixture builder — tenant/outlet/user vary per test, so build lazily."""

    def _make_tenant_outlet(self, country="AE", gst_inclusive=True):
        tenant = Tenant.objects.create(name="UAE VAT Test Tenant", country=country)
        outlet = Outlet.objects.create(
            tenant=tenant, name="Dubai Branch", gst_inclusive=gst_inclusive,
        )
        PaymentConfig.objects.create(tenant=tenant, outlet=outlet, cash_enabled=True)
        owner = User.objects.create_user(
            username=f"uae_owner_{tenant.id}", password="testpass",
            tenant=tenant, outlet=outlet, role="owner",
        )
        category = MenuCategory.objects.create(tenant=tenant, outlet=outlet, name="Food")
        return tenant, outlet, owner, category

    def _make_item(self, tenant, outlet, category, price, gst_percentage, name="Item"):
        return MenuItem.objects.create(
            tenant=tenant, outlet=outlet, category=category,
            name=name, price=price, gst_percentage=gst_percentage,
        )

    def _make_order(self, tenant, outlet, owner, item_specs):
        """item_specs: list of (menu_item, qty, price, gst_percentage)."""
        order = Order.objects.create(
            tenant=tenant, outlet=outlet, created_by=owner,
            source="counter", status="closed",
        )
        for menu_item, qty, price, gst_pct in item_specs:
            OrderItem.objects.create(
                order=order, menu_item=menu_item, quantity=qty,
                price=price, gst_percentage=gst_pct, total_price=price * qty,
            )
        order.recalculate_totals()
        order.refresh_from_db()
        return order

    def _bill_text(self, order, chars=48):
        raw = base64.b64decode(_build_receipt_b64(order, chars, "full", "cp437"))
        return raw.decode("cp437", errors="replace")

    def _bill_body_direct(self, order):
        """Build ESC/POS bytes by calling _print_bill_body directly (bypasses printer lookup)."""
        svc = PrintingService(chars_per_line=48)
        buf = BP()
        svc._print_bill_body(buf, order)
        return buf.buf.decode("cp437", errors="replace")

    def _render_html(self, owner, order):
        client = Client()
        client.force_login(owner)
        url = reverse("thermal-receipt", args=[order.id])
        resp = client.get(url)
        return resp


# ── Scenario 1: Golden path — AE + gst_inclusive, uniform 5% VAT ──────────────

class GoldenPathUAETests(UAEVatReceiptBase):

    def setUp(self):
        self.tenant, self.outlet, self.owner, self.category = self._make_tenant_outlet(
            country="AE", gst_inclusive=True,
        )
        self.item = self._make_item(self.tenant, self.outlet, self.category,
                                     price=Decimal("14.00"), gst_percentage=Decimal("5"),
                                     name="Shawarma")
        self.order = self._make_order(
            self.tenant, self.outlet, self.owner,
            [(self.item, 1, Decimal("14.00"), Decimal("5"))],
        )

    def test_math_back_calculation(self):
        # gst = 14 * 5/105 = 0.6666... -> rounds to 0.67; subtotal = 14 - 0.67 = 13.33
        self.assertEqual(self.order.gst_total, Decimal("0.67"))
        self.assertEqual(self.order.subtotal, Decimal("13.33"))
        self.assertEqual(self.order.grand_total, Decimal("14"))

    def test_effective_vat_rate_uniform(self):
        self.assertEqual(self.order.effective_vat_rate, Decimal("5"))

    def test_escpos_bill_body_has_uae_wording(self):
        text = self._bill_body_direct(self.order)
        self.assertIn("Total before VAT", text)
        self.assertIn("VAT @ 5%", text)
        self.assertIn("Net Amount", text)
        self.assertIn("Tax Inclusive - prices include VAT", text)
        self.assertNotIn("Subtotal", text)
        self.assertNotIn("TOTAL\n", text)  # old bold TOTAL line should not appear literally

    def test_qz_receipt_b64_pipeline_has_uae_wording(self):
        """Also sanity-check via the real _build_receipt_b64 pipeline used by the print queue."""
        text = self._bill_text(self.order)
        self.assertIn("Total before VAT", text)
        self.assertIn("VAT @ 5%", text)
        self.assertIn("Net Amount", text)

    def test_html_template_renders_uae_wording(self):
        resp = self._render_html(self.owner, self.order)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn("Total before VAT", html)
        self.assertIn("VAT @ 5%", html)
        self.assertIn("Net Amount", html)
        self.assertIn("Tax Inclusive", html)

    def test_html_template_has_correct_arabic_unicode(self):
        resp = self._render_html(self.owner, self.order)
        html = resp.content.decode("utf-8")
        self.assertIn("فاتورة ضريبية", html)
        self.assertIn("تاريخ", html)
        self.assertIn("قبل الضريبة", html)
        self.assertIn("الضريبة", html)
        self.assertIn("إجمالي المبلغ", html)
        self.assertIn("شامل الضريبة", html)

    def test_html_font_stack_includes_arabic_fallback(self):
        resp = self._render_html(self.owner, self.order)
        html = resp.content.decode("utf-8")
        self.assertIn("Noto Naskh Arabic", html)


# ── Scenario 2: Mixed-rate order (0% + 5%) ─────────────────────────────────────

class MixedRateUAETests(UAEVatReceiptBase):

    def setUp(self):
        self.tenant, self.outlet, self.owner, self.category = self._make_tenant_outlet(
            country="AE", gst_inclusive=True,
        )
        self.item_zero = self._make_item(self.tenant, self.outlet, self.category,
                                          price=Decimal("10.00"), gst_percentage=Decimal("0"),
                                          name="Bottled Water")
        self.item_five = self._make_item(self.tenant, self.outlet, self.category,
                                          price=Decimal("14.00"), gst_percentage=Decimal("5"),
                                          name="Shawarma")
        self.order = self._make_order(
            self.tenant, self.outlet, self.owner,
            [
                (self.item_zero, 1, Decimal("10.00"), Decimal("0")),
                (self.item_five, 1, Decimal("14.00"), Decimal("5")),
            ],
        )

    def test_effective_vat_rate_is_none_for_mixed_rates(self):
        self.assertIsNone(self.order.effective_vat_rate)

    def test_escpos_shows_plain_vat_no_percentage(self):
        text = self._bill_body_direct(self.order)
        self.assertIn("VAT", text)
        self.assertNotIn("VAT @", text)

    def test_html_shows_plain_vat_no_percentage(self):
        resp = self._render_html(self.owner, self.order)
        html = resp.content.decode("utf-8")
        self.assertIn("VAT", html)
        self.assertNotIn("VAT @", html)


# ── Scenario 3: Zero-rated uniform order (all items 0%) ───────────────────────

class ZeroRatedUniformUAETests(UAEVatReceiptBase):

    def setUp(self):
        self.tenant, self.outlet, self.owner, self.category = self._make_tenant_outlet(
            country="AE", gst_inclusive=True,
        )
        self.item = self._make_item(self.tenant, self.outlet, self.category,
                                     price=Decimal("10.00"), gst_percentage=Decimal("0"),
                                     name="Bottled Water")
        self.order = self._make_order(
            self.tenant, self.outlet, self.owner,
            [(self.item, 1, Decimal("10.00"), Decimal("0"))],
        )

    def test_effective_vat_rate_is_decimal_zero_not_none(self):
        rate = self.order.effective_vat_rate
        self.assertIsNotNone(rate)
        self.assertEqual(rate, Decimal("0"))

    def test_gst_total_is_zero_falsy_value(self):
        # Confirms the edge case: gst_total is Decimal('0.00'), which is falsy in Python.
        self.assertEqual(self.order.gst_total, Decimal("0.00"))
        self.assertFalse(bool(self.order.gst_total))

    def test_escpos_shows_vat_at_0_percent_despite_zero_gst_total(self):
        # gst_total is Decimal('0.00') (falsy) for an all-zero-rated order.
        # _print_bill_body must still print "VAT @ 0%" on the AE+inclusive path
        # for parity with the HTML template's `!= None` handling — previously
        # this line was silently dropped because the printer code only gated
        # on `if order.gst_total:` (fixed as part of this QA pass).
        text = self._bill_body_direct(self.order)
        self.assertIn("Total before VAT", text)
        self.assertIn("VAT @ 0%", text)

    def test_html_shows_vat_at_0_percent_not_plain_vat(self):
        """The specific edge case: `{% if order.effective_vat_rate != None %}` must
        distinguish Decimal('0') (falsy) from None, so a 0%-VAT order still shows
        'VAT @ 0%' rather than falling back to plain 'VAT'."""
        resp = self._render_html(self.owner, self.order)
        html = resp.content.decode("utf-8")
        self.assertIn("VAT @ 0%", html)


# ── Scenario 4: India / non-AE / AE-exclusive regressions ─────────────────────

class RegressionNonUAETests(UAEVatReceiptBase):

    def test_india_tenant_uses_old_wording_escpos(self):
        tenant, outlet, owner, category = self._make_tenant_outlet(
            country="IN", gst_inclusive=True,
        )
        item = self._make_item(tenant, outlet, category, price=Decimal("100.00"),
                                gst_percentage=Decimal("5"), name="Dosa")
        order = self._make_order(tenant, outlet, owner,
                                  [(item, 1, Decimal("100.00"), Decimal("5"))])
        text = self._bill_body_direct(order)
        self.assertNotIn("Total before VAT", text)
        self.assertNotIn("Net Amount", text)
        self.assertIn("TOTAL", text)

    def test_india_tenant_uses_old_wording_html(self):
        tenant, outlet, owner, category = self._make_tenant_outlet(
            country="IN", gst_inclusive=True,
        )
        item = self._make_item(tenant, outlet, category, price=Decimal("100.00"),
                                gst_percentage=Decimal("5"), name="Dosa")
        order = self._make_order(tenant, outlet, owner,
                                  [(item, 1, Decimal("100.00"), Decimal("5"))])
        resp = self._render_html(owner, order)
        html = resp.content.decode("utf-8")
        self.assertNotIn("Total before VAT", html)
        self.assertNotIn("Net Amount", html)
        self.assertNotIn("فاتورة ضريبية", html)  # gated on country == 'AE' only

    def test_ae_exclusive_pricing_uses_old_wording_escpos(self):
        """AE tenant but gst_inclusive=False — gating requires BOTH conditions."""
        tenant, outlet, owner, category = self._make_tenant_outlet(
            country="AE", gst_inclusive=False,
        )
        item = self._make_item(tenant, outlet, category, price=Decimal("100.00"),
                                gst_percentage=Decimal("5"), name="Shawarma")
        order = self._make_order(tenant, outlet, owner,
                                  [(item, 1, Decimal("100.00"), Decimal("5"))])
        text = self._bill_body_direct(order)
        self.assertNotIn("Total before VAT", text)
        self.assertNotIn("Net Amount", text)
        self.assertIn("Subtotal", text)
        self.assertIn("TOTAL", text)

    def test_ae_exclusive_pricing_uses_old_totals_block_html(self):
        tenant, outlet, owner, category = self._make_tenant_outlet(
            country="AE", gst_inclusive=False,
        )
        item = self._make_item(tenant, outlet, category, price=Decimal("100.00"),
                                gst_percentage=Decimal("5"), name="Shawarma")
        order = self._make_order(tenant, outlet, owner,
                                  [(item, 1, Decimal("100.00"), Decimal("5"))])
        resp = self._render_html(owner, order)
        html = resp.content.decode("utf-8")
        # Totals block must use the old Subtotal/TOTAL markup (gated on
        # country=='AE' and gst_inclusive together), even though the AE-only
        # "TAX INVOICE" heading and "Date / تاريخ" label ARE expected to appear
        # (those are gated on country=='AE' alone, by design).
        self.assertNotIn("Total before VAT", html)
        self.assertNotIn("Net Amount", html)
        self.assertIn("TAX INVOICE", html)
        self.assertIn("فاتورة ضريبية", html)
