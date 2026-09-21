import { test, expect, Page } from '@playwright/test';
import { TENANT_SLUG, E2E_TAG, uniqueUsername, runDjangoShell } from '../fixtures/testData';

/**
 * Brand-new "webstore" feature: a friendly-URL, no-QR-code ordering flow
 * (webstore/urls.py + webstore/views.py + webstore/templates/webstore/*.html).
 * A customer registers a webstore.CustomerAccount (a session identity fully
 * separate from accounts.User), logs in, browses the tenant's menu at
 * /<tenant_slug>/, and places a delivery order (name + phone + delivery
 * address are all mandatory -- there's no table/QR context to fall back on).
 *
 * Steps share one browser context/page on purpose (test.describe.serial +
 * a page created in beforeAll) since later steps depend on the webstore
 * session cookie set by the register step.
 */
test.describe.serial('Webstore ordering (delivery, no QR code)', () => {
  const username = uniqueUsername('webstore');
  const password = 'testpass123';
  const customerName = `${E2E_TAG} Webstore Customer`;
  const phone = '9876500001';
  const deliveryAddress = `${E2E_TAG} 123 Test Street, Test City`;

  let page: Page;
  let createdOrderId: number | null = null;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    // Cleanup MUST run even if closing the page/trace recording throws (seen
    // in practice as an ENOENT on the trace file) -- otherwise a harmless
    // teardown hiccup would leak the real DB rows this test created.
    try {
      if (createdOrderId) {
        runDjangoShell(
          `from orders.models import Order; Order.objects.filter(id=${createdOrderId}).delete()`
        );
      } else {
        // Fallback lookup in case we somehow never captured the id from the
        // create-order response -- find it by the distinctive E2E_TAG-tagged
        // delivery address instead, scoped to this test's own customer name.
        runDjangoShell(
          `from orders.models import Order; Order.objects.filter(delivery_address__icontains="${E2E_TAG}", customer_name="${customerName}").delete()`
        );
      }

      runDjangoShell(
        `from webstore.models import CustomerAccount; CustomerAccount.objects.filter(username="${username}").delete()`
      );
    } finally {
      await page.close().catch(() => {});
    }
  });

  /** Adds the first available menu item to the cart, handling an optional
   * required-modifier picker if the item happens to have one. */
  async function addFirstItemToCart() {
    await page.locator('.item-card .add-btn').first().click();

    const modifierModal = page.locator('#modifierModal');
    if (await modifierModal.evaluate((el) => el.classList.contains('active')).catch(() => false)) {
      // Pick the first option in every modifier group, then confirm.
      const groups = modifierModal.locator('.modifier-group-section');
      const groupCount = await groups.count();
      for (let i = 0; i < groupCount; i++) {
        await groups.nth(i).locator('.modifier-option').first().click();
      }
      await page.locator('.confirm-modifier-btn').click();
    }
  }

  test('register: a new customer account lands on the logged-in store page', async () => {
    await page.goto(`/${TENANT_SLUG}/register/`);

    await page.fill('input[name="name"]', customerName);
    await page.fill('input[name="phone"]', phone);
    await page.fill('input[name="username"]', username);
    await page.fill('input[name="password"]', password);
    await page.click('button.btn-submit[type="submit"]');

    await expect(page).toHaveURL(new RegExp(`/${TENANT_SLUG}/?$`));
    await expect(page).not.toHaveURL(/\/(login|register)\//);
    await expect(page.locator('.branch-info')).toContainText(customerName);
  });

  test('menu: category tabs and at least one item card are visible', async () => {
    await expect(page.locator('.cat-tab').first()).toBeVisible();
    await expect(page.locator('.item-card').first()).toBeVisible();
  });

  test('cart: adding an item opens checkout with name/phone prefilled and address empty', async () => {
    await addFirstItemToCart();

    await expect(page.locator('.cart-bar')).toHaveClass(/visible/);
    await page.locator('.view-cart-btn').click();
    await expect(page.locator('#cartModal')).toHaveClass(/active/);

    await expect(page.locator('#custName')).toHaveValue(customerName);
    await expect(page.locator('#custPhone')).toHaveValue(phone);
    await expect(page.locator('#custAddress')).toHaveValue('');
  });

  test('checkout: placing the order with an empty delivery address is blocked', async () => {
    await expect(page.locator('#custAddress')).toHaveValue('');

    let requestFired = false;
    const onRequest = (req: import('@playwright/test').Request) => {
      if (req.url().includes('/create-order/')) requestFired = true;
    };
    page.on('request', onRequest);

    await page.locator('#placeOrderBtn').click();
    await expect(page.locator('#custAddressError')).toHaveClass(/show/);
    await expect(page.locator('#custAddress')).toHaveClass(/input-error/);
    // Still on the checkout modal -- no navigation, no order created.
    await expect(page.locator('#cartModal')).toHaveClass(/active/);

    page.off('request', onRequest);
    expect(requestFired).toBe(false);
  });

  test('checkout: filling the delivery address places the order and shows the tracker', async () => {
    await page.fill('#custAddress', deliveryAddress);

    const [response] = await Promise.all([
      page.waitForResponse(
        (resp) => resp.url().includes('/create-order/') && resp.request().method() === 'POST'
      ),
      page.locator('#placeOrderBtn').click(),
    ]);

    expect(response.ok()).toBe(true);
    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.order_id).toBeTruthy();
    createdOrderId = body.order_id;

    await expect(page.locator('#orderPlacedView')).toHaveClass(/active/, { timeout: 10_000 });
    await expect(page.locator('.order-placed-title')).toHaveText(/Order Placed!/i);
    await expect(page.locator('#fsStatusStages .status-stage')).toHaveCount(4);
    await expect(page.locator('#fsOrderMeta')).toContainText(String(createdOrderId));

    // Close the full-screen tracker so later steps can reach the header again.
    await page.locator('.continue-shopping-btn').click();
    await expect(page.locator('#orderPlacedView')).not.toHaveClass(/active/);
  });

  test('logout: clears the session so / redirects back to login', async () => {
    await page.locator(`a[href$="/${TENANT_SLUG}/logout/"]`).click();
    await expect(page).toHaveURL(new RegExp(`/${TENANT_SLUG}/login/?$`));

    await page.goto(`/${TENANT_SLUG}/`);
    await expect(page).toHaveURL(new RegExp(`/${TENANT_SLUG}/login/?$`));
  });

  test('login: the same registered username/password works again', async () => {
    await page.goto(`/${TENANT_SLUG}/login/`);

    await page.fill('input[name="username"]', username);
    await page.fill('input[name="password"]', password);
    await page.click('button.btn-submit[type="submit"]');

    await expect(page).toHaveURL(new RegExp(`/${TENANT_SLUG}/?$`));
    await expect(page).not.toHaveURL(/\/login\//);
    await expect(page.locator('.branch-info')).toContainText(customerName);
  });
});
