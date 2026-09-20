# Full Product Demo: EasyBillBro (60s)

Built outside /brag's normal 15-25s teaser format at the user's explicit request — a full narrated walkthrough (login → in-app product tour) rather than a short hook video. Same Hyperframes pipeline, same music/voice/SFX conventions as the earlier 19s brag video, extended pacing.

## Brand (current, confirmed against live templates this session)
- Product name: **EasyBillBro** (renamed from Lexnorax elsewhere in the repo during this session — confirmed current by the user)
- Palette: cream `#F7F7F9` bg, white panels, red `#EC2734` primary accent, orange `#FA7327` secondary, near-black brown `#2C170E` ink, rounded corners (8-20px scale), pill buttons/tabs/badges
- Fonts: DM Serif Display (headings), Outfit (body), Space Mono (numbers/prices)
- Login page reference: `accounts/templates/accounts/login.html` — split screen, black/red-grid left panel with quote + stats (60s / ₹999 / GST), white right panel with EasyBillBro logo + username/password fields + red "Sign In →" pill button
- Dashboard reference: `orders/templates/orders/orders_dashboard.html` — sidebar (Orders/Kitchen/Tables/Live Floor/Waiter Calls/Customers), KPI tiles for Active/Served/Today's Orders
- Flagship feature: AI Menu Import (photo → menu items populate → countdown under 60s)

## Storyboard (60s, 9 scenes)
1. **Hook** — 0-4s — hero line "Your restaurant. Finally running like it should."
2. **Login** — 4-11s (7s) — recreate the split-screen login page; simulate typing + Sign In click
3. **Dashboard reveal** — 11-19s (8s) — sidebar + topbar + KPI tiles (Active/Served/Today's Orders)
4. **AI Menu Import** — 19-27s (8s) — flagship feature, menu rows populate, countdown settles
5. **Tables / Floor** — 27-34s (7s) — stat pills (Total/Free/Occupied) + table cards, color-coded status
6. **Kitchen display** — 34-40s (6s) — order tickets with status pills, station tabs
7. **Reports / Analytics** — 40-47s (7s) — KPI tiles + simple bar chart + "Top Selling Items"
8. **Highlight claims** — 47-53s (6s) — "No annual contract. Cancel anytime."
9. **Outro** — 53-60s (7s) — EasyBillBro wordmark + "₹999/month. No contract. Built in Bengaluru."

## Audio
- Music: reused `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (109.96 BPM, polished), re-extracted to a 60s audio-data window for audio-reactive glow.
- Voice: Kokoro `af_heart`, 9 lines, one per scene (see composition-brief.md for exact text + durations once generated).
- Soft beat-lock candidates found in-window: ~10.93s (scene 2→3), ~39.82s (scene 6→7), ~46.93s (scene 7→8) — used as soft transition bias only.

## Output
- `brag-output-fullproduct/brag.mp4` (target ~60s, 1920x1080)
- `brag-output-fullproduct/composition/` — Hyperframes project
