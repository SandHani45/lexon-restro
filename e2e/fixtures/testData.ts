/**
 * Shared test fixtures for the E2E suite. These tests run against the REAL
 * local dev server and its real database (there's no separate Playwright
 * test-DB, unlike Django's own test runner) -- so:
 *   1. Never invent data that could collide with real records; always use
 *      the `E2E_TAG` prefix/marker below for anything you create.
 *   2. Every spec that creates data (a webstore account, an order) MUST
 *      clean it up in an `afterAll` via `runDjangoShell()` below.
 *   3. Never mutate or delete pre-existing data outside what your own test
 *      created (e.g. don't touch other orders/tables for tenant "leo").
 */
import { execSync } from 'child_process';
import path from 'path';

export const E2E_TAG = 'E2E_TEST';

// Known-good seed data already present in the dev DB (tenant "leo"), used
// throughout this session's manual verification -- read-only fixtures,
// never mutated by tests.
export const STAFF = {
  username: 'leo',
  password: 'leo@12345',
};

export const TENANT_SLUG = 'leo';
export const TABLE_QR_TOKEN = 'e3aea676-4554-4f8f-9949-e35fcb9c1531';

/** A unique webstore username per test run, so repeated runs never collide. */
export function uniqueUsername(prefix: string): string {
  return `${E2E_TAG.toLowerCase()}_${prefix}_${Date.now()}`;
}

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const PYTHON = path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe');

/**
 * Runs a Python one-liner through `manage.py shell` for setup/teardown that
 * has no HTTP equivalent (e.g. deleting a test-created CustomerAccount/Order,
 * or toggling a feature flag). Kept to plain, idempotent one-liners --
 * this is test plumbing, not a place to reimplement app logic.
 */
export function runDjangoShell(code: string): string {
  return execSync(`"${PYTHON}" manage.py shell -c "${code.replace(/"/g, '\\"')}"`, {
    cwd: REPO_ROOT,
    encoding: 'utf-8',
  });
}
