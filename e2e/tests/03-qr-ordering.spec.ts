import { test, expect } from '@playwright/test';
import { TABLE_QR_TOKEN, E2E_TAG, runDjangoShell } from '../fixtures/testData';

/**
 * Covers the anonymous, unauthenticated QR-code table-ordering flow served
 * by menu/templates/menu/digital_menu.html at /menu/<uuid:qr_token>/:
 * browse the menu, add an item to the cart, view the cart, get blocked when
 * the (required) guest name is missing, then place a real order and land on
 * the full-screen "Order Placed" tracker.
 *
 * This hits the real dev server + real dev DB (no separate Playwright test
 * DB) and creates one real Order row -- it is deleted in afterEach below,
 * using the exact id captured from the /create-order/ response, mirroring
 * the manual cleanup pattern used throughout this app's development:
 *   Order.objects.get(id=<id>).items.all().delete()
 *   Order.objects.get(id=<id>).delete()
 */

const GUEST_NAME = `${E2E_TAG} QR Test`;

test.describe('Anonymous QR table ordering', () => {
  let createdOrderId: number | null = null;

  test.afterEach(async () => {
    if (createdOrderId !== null) {
      const id = createdOrderId;
      createdOrderId = null;
      runDjangoShell(
        `from orders.models import Order; Order.objects.get(id=${id}).items.all().delete(); Order.objects.get(id=${id}).delete(); print('E2E_CLEANED_UP')`
      );
    }
  });

  test('guest browses menu, is blocked without a name, then places an order', async ({ page }) => {
    await page.goto(`/menu/${TABLE_QR_TOKEN}/`);

    // --- 1/2: menu content loads ---
    const catTabs = page.locator('.cat-tab');
    await expect(catTabs.first()).toBeVisible();
    expect(await catTabs.count()).toBeGreaterThan(0);

    const itemCards = page.locator('.item-card');
    await expect(itemCards.first()).toBeVisible();
    const itemCount = await itemCards.count();
    expect(itemCount).toBeGreaterThan(0);

    // --- 3: add an item to the cart via its "ADD +" button ---
    // Some real menu items have required modifier groups (color/size/etc.),
    // which opens a modifier picker instead of adding straight to the cart.
    // Skip those and use the first item that adds directly, so this test
    // doesn't depend on which specific items happen to have modifiers
    // configured for tenant "leo" today.
    const modifierModal = page.locator('#modifierModal');
    let addedName = '';

    for (let i = 0; i < itemCount; i++) {
      const card = itemCards.nth(i);
      const addBtn = card.locator('.add-btn');
      if (!(await addBtn.isVisible())) continue;

      await addBtn.click();
      await page.waitForTimeout(200);

      const modifierOpened = await modifierModal.evaluate((el) =>
        el.classList.contains('active')
      );
      if (modifierOpened) {
        await page.locator('#modifierModal .close-modal-btn').click();
        await expect(modifierModal).not.toHaveClass(/active/);
        continue;
      }

      addedName = (await card.locator('.item-name').innerText()).trim();
      // Confirm this specific item's control flipped from ADD to the qty
      // stepper.
      await expect(addBtn).toHaveClass(/hidden/);
      break;
    }

    expect(addedName, 'expected at least one menu item addable without a required modifier').not.toBe('');

    // --- 3 (cont'd): cart bar reflects the addition ---
    const cartBar = page.locator('#cartBar');
    await expect(cartBar).toHaveClass(/visible/);
    await expect(page.locator('#totalItems')).toHaveText('1');
    await expect(page.locator('#totalPrice')).not.toHaveText('0.00');

    // --- 4: open the cart, confirm the item + price appear ---
    await page.getByRole('button', { name: /view cart/i }).click();
    await expect(page.locator('#cartModal')).toHaveClass(/active/);
    await expect(page.locator('#cartItemsContainer .cart-item-name').first()).toHaveText(addedName);
    await expect(page.locator('#cartItemsContainer .cart-item-price').first()).toBeVisible();

    // --- 5: placing the order with an EMPTY name is blocked ---
    let createOrderRequestSeen = false;
    page.on('request', (req) => {
      if (req.url().includes('/create-order/')) createOrderRequestSeen = true;
    });

    const placeOrderBtn = page.locator('#placeOrderBtn');
    await expect(page.locator('#guestName')).toHaveValue('');
    await placeOrderBtn.click();

    await expect(page.locator('#guestNameError')).toHaveClass(/show/);
    await expect(page.locator('#guestName')).toHaveClass(/input-error/);
    // Blocked client-side: no network call, and still on the cart modal
    // rather than the post-order full-screen view.
    expect(createOrderRequestSeen).toBe(false);
    await expect(page.locator('#orderPlacedView')).not.toHaveClass(/active/);
    await expect(page.locator('#cartModal')).toHaveClass(/active/);

    // --- 6: fill in a name and place the order for real ---
    await page.locator('#guestName').fill(GUEST_NAME);

    const [createOrderResponse] = await Promise.all([
      page.waitForResponse(
        (resp) => resp.url().includes('/create-order/') && resp.request().method() === 'POST'
      ),
      placeOrderBtn.click(),
    ]);

    expect(createOrderResponse.ok()).toBe(true);
    const body = await createOrderResponse.json();
    expect(body.success).toBe(true);
    expect(typeof body.order_id).toBe('number');
    createdOrderId = body.order_id;

    // Full-screen "Order Placed" view with the 4-stage tracker.
    await expect(page.locator('#orderPlacedView')).toHaveClass(/active/, { timeout: 10_000 });
    await expect(page.getByText('Order Placed!')).toBeVisible();
    await expect(page.locator('#fsStatusStages .status-stage')).toHaveCount(4);
  });
});
