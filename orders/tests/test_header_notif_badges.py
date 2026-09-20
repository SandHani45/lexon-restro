# orders/tests/test_header_notif_badges.py
"""
billing.html and tables.html each hand-copied their own header notification
badges independently of core/base.html's defaults -- both had only the
"Calls" (waiter/kitchen) badge, missing the QR-orders badge entirely, and
neither could have the low-stock/system badge since it didn't exist until
it was added centrally. Consolidated into two shared partials
(core/_notif_badges.html for icon-only headers, core/_notif_badges_luxury.html
for the POS screens' text+icon style) so all three badges stay in sync
across every page from one place instead of N hand-copies.

Run: python manage.py test orders.tests.test_header_notif_badges
"""
from django.test import TestCase, Client
from django.urls import reverse
from tenants.models import Tenant, Outlet
from accounts.models import User
from orders.models import Order


class HeaderNotifBadgeConsistencyTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Badge Tenant", tenant_type="fine_dining")
        self.outlet = Outlet.objects.create(tenant=self.tenant, name="Main")
        self.manager = User.objects.create_user(
            username="badge_mgr", password="pw", role="manager",
            tenant=self.tenant, outlet=self.outlet,
        )
        self.waiter = User.objects.create_user(
            username="badge_waiter", password="pw", role="waiter",
            tenant=self.tenant, outlet=self.outlet,
        )
        from menu.models import MenuCategory, MenuItem
        cat = MenuCategory.objects.create(tenant=self.tenant, outlet=self.outlet, name="General")
        MenuItem.objects.create(tenant=self.tenant, outlet=self.outlet, category=cat, name="Test Item", price=10)
        self.client = Client()

    def _login(self, user):
        self.client.login(username=user.username, password="pw")

    def test_manager_sees_system_alerts_badge_on_billing(self):
        self._login(self.manager)
        resp = self.client.get("/billing/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="notif-badge-system"', resp.content.decode())

    def test_manager_sees_system_alerts_badge_on_tables(self):
        self._login(self.manager)
        resp = self.client.get("/tables/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="notif-badge-system"', resp.content.decode())

    def test_waiter_does_not_see_system_alerts_badge_on_billing(self):
        self._login(self.waiter)
        resp = self.client.get("/billing/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('id="notif-badge-system"', resp.content.decode())

    def test_billing_now_shows_qr_orders_badge_too(self):
        """
        The badge billing.html was missing entirely before consolidation,
        not just the new one -- fine_dining has both qr_menu and
        floor_plan, so this should now render for a non-chef role.
        """
        self._login(self.manager)
        resp = self.client.get("/billing/")
        self.assertIn('id="notif-badge-qr"', resp.content.decode())

    def test_waiter_calls_badge_still_present_on_billing(self):
        """Regression guard -- the one badge that DID already work must
        not have been lost in the consolidation."""
        self._login(self.manager)
        resp = self.client.get("/billing/")
        content = resp.content.decode()
        self.assertIn('id="notif-badge-waiter"', content)
        self.assertIn('id="notif-badge-waiter-mobile"', content)

    def test_mobile_badges_hidden_on_desktop_not_shown_twice(self):
        """
        Real bug, caught live: the luxury partial's desktop row is
        correctly wrapped in d-sm-none/d-sm-inline-flex, but the mobile
        row underneath it (a separate include of the icon-only partial)
        had no visibility class applied at all -- so both the labeled
        desktop badges ("Calls", "QR Orders", "Alerts") AND the icon-only
        mobile duplicates rendered at every screen size simultaneously,
        four extra icons appearing on a plain desktop screenshot.
        """
        self._login(self.manager)
        resp = self.client.get("/billing/")
        content = resp.content.decode()
        # the mobile-suffixed wrapper must carry d-sm-none so it's hidden
        # at the same breakpoint the desktop row switches on at
        import re
        mobile_wrapper = re.search(
            r'<span class="notif-wrapper[^"]*d-sm-none[^"]*"[^>]*>\s*<a href="/waiter-dashboard/" class="btn-icon"',
            content,
        )
        self.assertIsNotNone(mobile_wrapper, "mobile icon-only Calls wrapper not found")
        self.assertIn("d-sm-none", mobile_wrapper.group(0))

    def test_billing_desktop_calls_badge_is_clean_bell_icon(self):
        """
        Billing header desktop Calls badge must be the clean circular bell icon
        (btn-icon) matching the order header, rather than the text button btn-luxury.
        """
        self._login(self.manager)
        resp = self.client.get("/billing/")
        content = resp.content.decode()
        import re
        desktop_calls = re.search(
            r'<span class="notif-wrapper[^"]*d-none d-sm-inline-flex[^"]*"[^>]*>\s*<a href="/waiter-dashboard/" class="btn-icon"[^>]*title="Calls">\s*<i class="bi bi-bell"></i>\s*</a>',
            content,
        )
        self.assertIsNotNone(desktop_calls, "Desktop Calls badge should be a btn-icon with bell icon")

    def test_universal_bell_icon_rendered_on_all_pages(self):
        """
        Notification bell icon must be present across all application page headers,
        even pages that override header_right (e.g. order history, tables, billing).
        """
        self._login(self.manager)
        for url in ["/billing/", "/tables/", "/orders/history/", "/dashboard/"]:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, f"Failed loading {url}")
            self.assertIn('id="notif-badge-waiter"', resp.content.decode(), f"Bell icon badge missing on {url}")

    def test_profile_details_positioned_last_in_topbar(self):
        """
        User profile details (.user-role-badge) must ALWAYS appear at the very end
        (top right last) of the .topbar-right container, after action buttons and notifications.
        """
        self._login(self.manager)
        for url in ["/billing/", "/tables/", "/orders/history/"]:
            resp = self.client.get(url)
            content = resp.content.decode()
            notif_idx = content.find('id="notif-badge-waiter"')
            profile_idx = content.find('class="user-role-badge"')
            self.assertNotEqual(notif_idx, -1, f"notif badge not found on {url}")
            self.assertNotEqual(profile_idx, -1, f"user-role-badge not found on {url}")
            self.assertGreater(profile_idx, notif_idx, f"Profile details must be positioned after notification badges on {url}")

    def test_tables_no_longer_ships_its_own_redundant_poller(self):
        """
        The page-local 10s pollNotifications() duplicated the global 8s
        poller in base.html -- removed, not left running alongside it.
        Both happened to share the name "pollNotifications" (base.html's
        global one is scoped inside its own IIFE, so there was never an
        actual collision, just a coincidence) -- the 10000ms interval is
        what's actually unique to the deleted local one.
        """
        self._login(self.manager)
        resp = self.client.get("/tables/")
        self.assertNotIn("setInterval(pollNotifications, 10000)", resp.content.decode())

    def test_sidebar_orders_link_does_not_contain_notif_badge(self):
        """
        Regression guard: the sidebar 'Orders' link previously had
        notif-badge-waiter embedded inside it by mistake, which caused
        kitchen-ready and waiter-call notifications to display on the
        'Orders' sidebar item instead of on the notification bell icon.
        """
        self._login(self.manager)
        resp = self.client.get("/tables/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        import re
        orders_link = re.search(r'<a\s+href="/orders/"[^>]*>(.*?)</a>', content, re.DOTALL)
        self.assertIsNotNone(orders_link, "Sidebar Orders link not found")
        self.assertNotIn("notif-badge", orders_link.group(1), "Orders sidebar link should not have a notification badge")


class TokenBillingHeaderBadgeTest(TestCase):
    """
    Cafe/QSR tenants don't have waiter_call or qr_menu in their default
    feature set (no waiter-run floor, no table-based QR ordering) -- so on
    token_billing.html, only the low-stock/system badge is expected to
    ever actually render for them. This is exactly the "for QSR mode I
    don't need that" distinction the badges' own role/feature gates
    already handle correctly, not something token_billing.html needed to
    special-case itself.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(name="QSR Badge Tenant", tenant_type="cafe")
        self.outlet = Outlet.objects.create(tenant=self.tenant, name="Main")
        self.manager = User.objects.create_user(
            username="qsr_badge_mgr", password="pw", role="manager",
            tenant=self.tenant, outlet=self.outlet,
        )
        self.order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, status="open",
        )
        self.client = Client()
        self.client.login(username="qsr_badge_mgr", password="pw")

    def test_system_alerts_badge_shows_for_qsr_manager(self):
        resp = self.client.get(reverse("token-bill", args=[self.order.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="notif-badge-system"', resp.content.decode())

    def test_waiter_call_badge_does_not_show_for_qsr_tenant(self):
        """cafe/QSR tenant types don't have waiter_call by default -- the
        badge gate hides it correctly rather than showing a dead link."""
        resp = self.client.get(reverse("token-bill", args=[self.order.id]))
        self.assertNotIn('id="notif-badge-waiter"', resp.content.decode())
