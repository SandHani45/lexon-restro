import { test, expect } from '@playwright/test';

/**
 * Public one-click "Live Demo" flow (accounts/views/auth_views.py ::
 * demo_login). GET /live-demo/ is unauthenticated and passwordless: it logs
 * the visitor straight into the pre-seeded "Demo Bistro" owner account and
 * redirects to the live floor plan at /tables/ (the most immediately
 * convincing view, not the analytics dashboard). No form/credentials here,
 * so there's no negative case to test -- just that the one-click path works
 * and the visitor ends up genuinely authenticated.
 */
test.describe('Live demo', () => {
  test('one-click entry logs the visitor in and lands on the live floor plan', async ({ page }) => {
    await page.goto('/live-demo/');

    await expect(page).toHaveURL(/\/tables\/?$/);
    // The page's own sidebar nav also contains a same-text link/heading
    // ("Floor Plan & Tables" as the active nav item) alongside the page's
    // real subbar title -- scope to #pos-main so this doesn't strict-mode
    // violate by matching both.
    await expect(page.locator('#pos-main').getByRole('heading', { name: /Floor Plan/i })).toBeVisible();
  });

  test('the visitor is genuinely authenticated (dashboard loads without bouncing to login)', async ({ page }) => {
    await page.goto('/live-demo/');
    await expect(page).toHaveURL(/\/tables\/?$/);

    await page.goto('/dashboard/');
    await expect(page).toHaveURL(/\/dashboard\/?$/);
    await expect(page).not.toHaveURL(/\/login\//);
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  });
});
