# TeamScout frontend

Next.js App Router UI for Feature 1 (resume → jobs → team) and Feature 2 (library → best resume).

## Stack

- Next.js + React 19 + TypeScript
- Tailwind CSS v4 (design tokens in `app/globals.css`)
- `@tanstack/react-query` for server state
- `framer-motion` for motion (respects `prefers-reduced-motion`)
- `sonner` toasts (errors include request id when present)
- `lucide-react` icons
- Playwright e2e under `e2e/`

## Scripts

```bash
pnpm install
pnpm dev          # http://localhost:3000
pnpm typecheck
pnpm test         # vitest
pnpm build
pnpm test:e2e     # Playwright (mocks API via route interception)
```

Set `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`).

Optional: `NEXT_PUBLIC_GITHUB_BASE` (e.g. `https://github.com/org/repo/blob/main`) enables clickable Engineering principles links on `/about`. When unset, paths render as plain text (never placeholder `OWNER/teamscout` URLs).

## Design

- Dark-mode-first with light toggle (cookie `teamscout-theme`, class strategy, pre-paint script in `layout.tsx`; no browser storage APIs)
- Geist Sans + Geist Mono for scores, credits, and IDs
- One accent for primary actions / scores; 8px grid

## Credit-safe mutations

All mutations use `retry: false` (QueryClient defaults + explicit on upload/search/find-team/reveal/recommend).

## Lighthouse

Not measured in automated CI. Manual target guidance: Performance ≥85, Accessibility ≥95, Best Practices ≥95. Run locally against a production build if you need numbers — do not claim scores without a run.

## Screenshots

E2E writes six screenshots under `public/screenshots/` when `pnpm test:e2e` runs:

1. `01-wizard-upload.png`
2. `02-profile-confirm.png`
3. `03-job-matches.png`
4. `04-team-discovery.png`
5. `05-library.png`
6. `06-resume-comparison.png`
7. `07-about.png` (About story — journeys + funnel)
