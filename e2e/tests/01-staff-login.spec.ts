import { test, expect } from '@playwright/test';
import { STAFF } from '../fixtures/testData';

/**
 * Staff/owner login flow via the shared /login/ form (accounts/views/auth_views.py
 * :: login_view, template accounts/templates/accounts/login.html). Every
 * tenant's staff use this same form -- tenant "leo" is just the one with
 * known-good credentials (see testData.ts). A successful owner/manager login
 * redirects to /dashboard/ (accounts/views/auth_views.py :: _role_path).
 */
test.describe('Staff login', () => {
  test('logs in with valid credentials and lands on the owner dashboard', async ({ page }) => {
    await page.goto('/login/');

    await page.locator('input[name="username"]').fill(STAFF.username);
    await page.locator('input[name="password"]').fill(STAFF.password);
    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page).toHaveURL(/\/dashboard\/?$/);
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  });

  test('rejects an invalid password and stays on the login page', async ({ page }) => {
    await page.goto('/login/');

    await page.locator('input[name="username"]').fill(STAFF.username);
    await page.locator('input[name="password"]').fill('definitely-not-the-password');
    await page.getByRole('button', { name: /sign in/i }).click();

    // login_view re-renders accounts/login.html (no redirect) with a
    // messages.error() -- URL must stay on /login/, never reach /dashboard/.
    await expect(page).toHaveURL(/\/login\/?$/);
    await expect(page.getByText('Invalid username or password.')).toBeVisible();
  });

  test('logout clears the session and locks /dashboard/ back to login', async ({ page }) => {
    await page.goto('/login/');
    await page.locator('input[name="username"]').fill(STAFF.username);
    await page.locator('input[name="password"]').fill(STAFF.password);
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/dashboard\/?$/);

    await page.getByRole('link', { name: 'Logout' }).click();
    await expect(page).toHaveURL(/\/login\/?$/);

    // Session is gone -- a direct hit on the login-gated dashboard must
    // bounce back to /login/ (Django's login_required using LOGIN_URL).
    await page.goto('/dashboard/');
    await expect(page).toHaveURL(/\/login\//);
  });
});
