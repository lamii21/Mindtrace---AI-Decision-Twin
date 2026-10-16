# MINDTRACE — frontend

Next.js 14 (App Router) + TypeScript + Tailwind CSS. A cinematic landing page plus a
functional decision workspace, wired to the real MINDTRACE backend (`../backend`) — no
fabricated data anywhere.

## Setup

```bash
cd frontend
npm install
```

Create `.env.local` (already present in this checkout, gitignored):

```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

## Running

The backend must be running first (see `../backend/README.md`), with CORS configured to
allow this app's origin (`MINDTRACE_CORS_ORIGINS`, default `http://localhost:3000` already
matches `npm run dev`'s default port).

```bash
npm run dev      # http://localhost:3000
npm run build    # production build
npm run lint     # eslint
npx tsc --noEmit # type-check
```

## What's real vs. illustrative

- **Landing page** (`/`): the hero's 3D scene, the four-twins section, and the uncertainty
  reasons are grounded in the real `schema/twins.yaml` and the real `UncertainReason` enum
  (`lib/twins.ts`). Section A's factor/evidence diagram is explicitly labeled illustrative —
  it does not call the API.
- **App** (`/app/*`): every page calls the real backend - register, login, decision
  creation, `/v1/simulate`, and the evidence chain (`/v1/evidence/decision_factor/{id}`).
  Nothing here is mocked or hardcoded; a failed request shows the backend's real
  `problem+json` error.

## Known gaps (see the final report for the full list)

- No audit-log timeline view - the backend exposes no `GET` endpoint for `AuditLog` yet.
- No Twin Read API view (`GET /v1/twins*`) - not implemented on the backend.
- The Twin Interview (cold-start elicitation) flow has no frontend yet.
- Visual/browser testing was not possible in this environment (no browser automation
  tool was available) - verified via build, lint, type-check, and direct `curl` checks of
  every route instead.
