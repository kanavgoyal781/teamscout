# M23 design-critical review notes

Reviewer lens: one expensive product, not default-shadcn or leftover dark-green.

## Verdict

**Pass with notes.** Screens share cream + dark navy tokens, Fraunces display, hairline surfaces, and brass-limited chrome. No functional changes.

## One product?

| Surface | Reads as editorial? | Flags fixed |
|---|---|---|
| Wizard / job cards | Yes — raised cream cards, navy score numbers mono | Score ring brass fill, navy track |
| Why-panel bars | Yes — single navy scale, opacity steps | Removed rainbow fills |
| Skill chips | Yes — navy-tint hit / warning outline miss | |
| Library / winner | Yes — brass top-border + Best match badge only | Removed trophy glow/ring |
| About diagrams | Yes — navy strokes; brass on active/flow only | Removed brass kickers, default node brass |
| Ops / empty / skeleton | Yes — cream shimmer, hairline panels | |
| Toasts / modals / tour | Overlay soft shadow only | Dropped sonner `richColors` |

## Brass discipline (three product uses + About active)

Sanctioned:

1. Score-ring progress stroke  
2. “Best match” badge (+ winner hairline top border as badge companion)  
3. Active nav inset indicator  

Also allowed: About **active/flow** highlight (selected diagram node, open journey step num, active weight segment, active video shot mark).

Not used for: section kickers, body links, principle marks, default funnel/node colors.

## Hairline visibility

- `--line` light: `rgba(12,31,63,0.12)` — may read soft on low-end laptop panels; cards also use `--border-strong` on hover/focus.  
- Dark: `rgba(242,237,226,0.14)`.  
- If field reports “invisible borders”, first lever is `--line` → 0.16 opacity (token-only).

## Dark-mode breakdown bars

- Fills use `--accent` (cream in dark) with opacity steps 1.0 → 0.4.  
- Extra rule: `html.dark .breakdown-row:nth-child(n+5)` floor opacity **0.55** so later bars stay legible on navy raised surfaces.

## Hardcoded colors

- Component TS/TSX: **near-zero** hex (enforced by `theme.tokens.test.ts`).  
- Hex lives in `globals.css` token block only.  
- Product CSS body: no neon/indigo/sky/emerald chip literals; facets use `--surface-hover` / `--accent-soft` only. Remaining raw `rgba(0,0,0,…)` is overlay scrim (tour/modal) only.  
- Single radius token `--radius: 10px` for facets, filter-hint, cards (no 6px/8px leftovers).  
- Orphaned old palette removed from tokens (see PR list).

## Orphaned old hex (deleted)

`#3dd68c`, `#1f8f5a`, `#176b44`, `#0c0d10`, `#14161c`, `#1a1d26`, `#181b23`, `#1f2330`, `#2a2f3c`, `#3a4154`, `#eceef4`, `#a0a8b8`, `#6b7385`, `#f6f5f2`, `#eeebe4`, `#e2ddd3`, `#cfc8ba`, `#16181d`, `#e8b84a`, `#f07178`, `#e8a87c`, `#a65d2e`, `#b8860b`, `#c0392b`, `#c4a35a` (old about brass literal), green match softs.

## Lighthouse / Playwright

- Target: a11y ≥95 both modes (manual Lighthouse when app is up).  
- Playwright e2e refreshes `public/screenshots/01–07` on happy-path runs (light default).  
- `prefers-reduced-motion` rules retained (skeleton animation off; motion helpers unchanged).
