# End-to-end tests (Playwright)

Covers the app's real, live user flows against the local dev server and its
real database — there's no separate Playwright test database, so every spec
that creates data (an order, a webstore account) tags it clearly and cleans
it up in an `afterEach`/`afterAll` hook. See `fixtures/testData.ts` for the
shared conventions (`E2E_TAG`, `uniqueUsername()`, `runDjangoShell()`).

## Setup (one-time)

```bash
npm install
npx playwright install chromium
```

## Running

Start the Django dev server first (`python manage.py runserver`) — the
config will reuse it. If nothing is listening on `:8000`, Playwright starts
one itself.

```bash
npm run test:e2e            # headless, full suite
npm run test:e2e:ui         # interactive UI mode, great for debugging
npm run test:e2e:report     # open the last HTML report
```

## What's covered (`e2e/tests/`)

| File | Flow |
|---|---|
| `00-smoke.spec.ts` | Landing page loads |
| `01-staff-login.spec.ts` | Staff/owner login, wrong-password rejection, logout |
| `02-live-demo.spec.ts` | Public one-click `/live-demo/` → Demo Bistro floor plan (requires the seed described below) |
| `03-qr-ordering.spec.ts` | Anonymous QR table ordering: browse → cart → mandatory-name validation → place order → status tracker |
| `04-webstore-ordering.spec.ts` | New no-QR browser ordering: register → login → cart prefill → mandatory delivery address → place order → logout → re-login |

## One-time dev-DB seed for the live-demo test

`02-live-demo.spec.ts` logs into a pre-seeded "Demo Bistro" tenant. If your
dev DB doesn't have one yet:

```bash
python manage.py reset_demo_tenant
```

This is the same command the app itself documents as safe to run by hand
(`orders/management/commands/reset_demo_tenant.py`) — idempotent, scoped
only to its own Demo Bistro tenant.

## A note on flakiness

Roughly 1 in a few runs, a test may report a `browserContext.close: ENOENT`
error while writing its trace/video artifacts *after* the test's own
assertions have already passed. This has been observed on this repo path
(likely OneDrive-sync file-lock contention, not a defect in the app or the
test) — re-running the affected spec on its own confirms it passes. If this
becomes disruptive in CI, consider moving the repo/checkout off a
sync-managed path, or setting `use.trace`/`use.video` to `'off'` in
`playwright.config.ts`.
