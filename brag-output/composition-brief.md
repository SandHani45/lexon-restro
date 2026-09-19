# Hyperframes Composition Brief: EasyBillBro

## Objective
Create a short launch-style brag video for EasyBillBro, a cloud POS platform for Indian restaurants.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: ~19s (voice-driven; see per-scene durations below)

## Source Material
- Project root: `C:\Users\sandh\Documents\Lexonit\Proposels\FoodApp\restaurant-pos`
- Primary files read: `public/index.html` (marketing landing page — full source, inline CSS), `README.md`, `CHANGELOG.md`
- Product name: EasyBillBro
- Tagline / strongest claim: "Your restaurant. Finally running like it should." Strongest demonstrable claim: AI menu import from a photo in under 60 seconds.
- Key UI or visual moment to recreate: the `.ai-visual` card from `public/index.html` — dark panel, three status dots, "AI MENU IMPORT" label, menu rows (name + gold price) that fade/slide in one at a time, a mono countdown timer beneath
- Copy that must appear verbatim:
  - "Your restaurant. Finally running like it should."
  - "AI MENU IMPORT" (card label)
  - Menu rows: Paneer Tikka ₹280, Garlic Naan ₹55, Dal Makhani ₹180, Mango Lassi ₹120, Chicken Biryani ₹320, Masala Chai ₹60
  - "No annual contract." / "Cancel anytime."
  - "EasyBillBro"
  - "₹999/month. No contract. Built in Bengaluru."

## Creative Direction
- Tone preset: polished
- Creative direction: premium boutique reveal — gold-on-black, restrained motion, founder-led confidence. Not a toy app, not a hype reel.
- Interpretation: slow, confident holds over quick cuts; one flourish per scene (the gold "Finally," the countdown, the logo settle) rather than many simultaneous motions; mixed-case type with generous letter-spacing; nothing shouts or oversells.
- Angle: The whole product pitch collapses into one demonstrable moment — point a phone at a menu, and EasyBillBro builds the real thing while you watch. The video lets that moment actually happen on screen, framed by the gold-on-black identity the product already uses to differentiate from dated Indian POS software.
- Hook: "Your restaurant." (white) → "Finally" (gold italic, half-beat later) → "running like it should." (muted white)
- Outro / punchline: Gold diamond mark → "EasyBillBro" wordmark → "₹999/month. No contract. Built in Bengaluru." — hold to black, no CTA button.
- Avoid:
  - Generic SaaS language ("streamline your workflow," etc. — not present in source copy, keep it that way)
  - Abstract filler visuals (no stock motion graphics, no unrelated icons)
  - Redesigning the product's identity — reuse the site's exact palette, fonts, and the AI-import card structure rather than inventing a new visual language

## Visual Identity
- Background: `#0a0a0a` (near-black), panel `#161616`, darker panel `#111111`
- Text: `#ffffff` (headlines), `rgba(255,255,255,0.5)` (secondary/sub copy), `rgba(255,255,255,0.3)` (tertiary/labels)
- Accent: `#c5a059` (gold), `#e8d5a3` (gold-light), `#9a7a3a` (gold-dark), border tint `rgba(197,160,89,0.15)`
- Display font: `DM Serif Display` (Google Fonts) — headline, wordmark, plan price
- Body font: `Outfit` (Google Fonts) — everything else
- Mono accent font: `Space Mono` (Google Fonts) — menu item prices, countdown timer
- Visual references from the project: the nav logo mark (32px square rotated 45°, gold, with a smaller black inset square — a diamond), the `.ai-visual` card (dark panel, 3 status dots in red/amber/green, bordered menu rows), the hairline grid background (`rgba(197,160,89,0.04)` lines, 60px grid, radial mask) used behind the hero

## Storyboard
Use the storyboard in `brag-output/brag-plan.md` as the creative contract. Final per-scene durations below are voice-driven (see Audio → Voiceover), adjusted from the plan's 5/7/3/4s split to fit the generated Kokoro narration plus settle time — sum is unchanged at 19s within one scene's rounding.

Scene summary:
1. Hook — 4.5s — hero line arrives in three staggered fragments on black; gold "Finally" is the one flourish
2. AI Menu Import — 7s — the `.ai-visual` card recreated; six menu rows arrive one by one with gold Space Mono prices; countdown ticks up and settles under 60s
3. No annual contract — 3.5s — two staggered lines, generous black space, polished restraint
4. Outro — 4s — diamond mark → wordmark → tagline → hold to black

## Audio
- Audio role: warm, restrained bed with a couple of tasteful accents, plus voiceover
- Audio arc: music bed enters with Scene 1 at low volume and stays under everything; ducks under each voiceover line; three quiet SFX accents mark the first menu row, the countdown settling, and the logo settling; bed fades out through the final hold
- Music: `assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (already copied into `composition/assets/music/`), volume ~0.30, no swell
- Music cue guidance: bundled preset copied to `composition/assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json` (109.96 BPM). Soft-bias targets only, never at the cost of readability or the voiceover: ~4.91s for the Scene 1→2 transition, ~8.74s (strong cue, 0.99) for the first menu-row pop-in, ~13.11s (strong cue, 0.98) for the Scene 2→3 transition. Treat as hints — the actual voice-driven scene durations below take priority over exact cue alignment.
- Audio-reactive treatment: subtle — let the hero's gold glow and the AI-import card's border/presence breathe slightly with music RMS. No waveform, no equalizer bars, no particle/visualizer graphics.
- Audio-coupled moments:
  - Scene 2, first menu row arrival — soft accent (card/drop-style SFX), not on every row
  - Scene 2, countdown settling under 60s — a slightly more present completion accent
  - Scene 4, logo mark settling — one quiet accent, the video's only "landing" sound
- SFX selection guidance: keep to 2-3 total cues, quiet, nothing aggressive — this is `polished`, not `default` or `chaotic`. A card/drop-style sound for the menu row, a soft bell/announcement-style sound for the countdown settle, a soft impact for the logo. Match family to the implemented animation once it exists.
- SFX analysis guidance: prefer low/medium high-frequency-risk files (`sfx-analysis.md` in the brag plugin's `skills/brag/assets/sfx/`) since these are repeated/polished moments, not one-off accents.
- Exact SFX choice: Hyperframes should choose exact filenames, timestamps, and volumes based on the implemented animation; copy any chosen SFX into `composition/assets/sfx/`.
- Audio files already copied into `composition/assets/`:
  - `composition/assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3`
  - `composition/assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json`
  - `composition/assets/voice/vo-1-hook.wav` (3.072s) — Scene 1: "Every restaurant deserves software that actually works."
  - `composition/assets/voice/vo-2-import.wav` (4.203s) — Scene 2: "Photograph your menu. EasyBillBro reads it, and builds it, in under a minute."
  - `composition/assets/voice/vo-3-contract.wav` (2.901s) — Scene 3: "Cancel anytime. Message the founder directly."
  - `composition/assets/voice/vo-4-outro.wav` (2.667s) — Scene 4: "EasyBillBro. Built for Indian restaurants."

### Voiceover
Voice is enabled (user passed `--voice`). Generated via Kokoro (`af_heart`), already rendered to the four WAV files above — do not regenerate. Wire each clip on its own track, one per scene, starting near that scene's start. Music ducks to ~0.12-0.15 under each voiceover clip and returns to ~0.30 between them. Scene durations in this brief already account for each clip's length plus settle time — do not shrink a scene below its voice clip's duration.

## Hyperframes Instructions
Load the composition-building Hyperframes domain skills — `hyperframes-core` (composition contract + `data-*` timing), `hyperframes-animation` (motion), `hyperframes-creative` (design spec, beats, audio-reactive), `hyperframes-keyframes` (seek-safe keyframes), and `hyperframes-cli` (lint/check/render). This is `/brag`'s own workflow: do not enter the `hyperframes` entry-point intent interview and do not route into its generic promo/launch-video workflow. Prefer native Hyperframes conventions over anything written here.

Requirements:
- Show at least one real UI, copy, or visual element from the source project (the AI Menu Import card is the centerpiece — required).
- Keep all text readable in the final render (respect the reading-time floor from `brag-plan.md`'s Step 2 guidance: short labels ~0.8s settled, sentences ~0.3s/word).
- Keep the video within 15-25 seconds (target ~19s per the voice-adjusted storyboard above).
- Include the music and SFX layer as specified — audio was not disabled.
- Treat the music cue guidance above as soft hints; voice-driven scene timing takes priority over exact beat alignment.
- Use SFX to support motion: a card/drop sound for the menu row, a soft announcement sound for the countdown settle, a soft impact for the logo settle. Keep total SFX to 2-3 cues at low volume, consistent with `polished` restraint.
- Wire the four voiceover clips into the composition per the Voiceover section above; duck music under each clip.
- Add subtle audio-reactive treatment (hero glow / AI-card presence breathing with music RMS) if the extraction helper is available; otherwise skip and note it rather than blocking the render.
- Run `hyperframes check` before render — it is `/brag`'s single gate.
