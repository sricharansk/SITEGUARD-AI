# Site Guard AI web app

The browser front end for Site Guard AI: incident reporting, the incident command center (evidence, AI
investigation, risk, corrective and preventive actions, verification and closure), the project dashboard, the CAPA
review board, knowledge search and the audit log.

Site Guard AI is decision support. Every AI output in the app is labelled "AI decision support, needs human
review", nothing an agent proposes is acted on until a person approves it, and the app never claims legal
compliance or certification.

## Stack

- Next.js 16 (App Router, `proxy.ts`), React 19, TypeScript (strict), Tailwind CSS 4.
- No UI kit and no data-fetching library: small hooks in `lib/hooks.ts` and plain components.
- Vitest + Testing Library for unit and component tests, Playwright for the browser E2E.
- Exact versions are pinned in `package.json`; `package-lock.json` is committed. Node 22.12 or later.

## Run it locally

```bash
make run           # API on http://localhost:8000 with demo data (SQLite, offline rules provider)
make web-install   # npm ci in frontend/
make web-dev       # web app on http://localhost:3000
```

Sign in with a demo account (password `siteguard-demo`, from `SITEGUARD_DEMO_PASSWORD`), for example
`hse@demo.siteguard.local` (HSE manager), `pm@demo.siteguard.local` (project manager) or
`auditor@demo.siteguard.local` (read-only auditor). All demo data is synthetic and labelled as such.

With Docker: `cp .env.example .env && docker compose up --build` starts PostgreSQL, the API and the web app on
http://localhost:3000.

Production build without Docker:

```bash
npm run build      # also copies static assets next to the standalone server
PORT=3000 SITEGUARD_API_URL=http://localhost:8000 npm start
```

## Configuration

All settings are read by the web app's server, never by the browser. For `npm run dev`, put them in
`frontend/.env.local` (git-ignored).

| Variable | Default | Purpose |
|---|---|---|
| `SITEGUARD_API_URL` | `http://localhost:8000` | Base URL of the FastAPI service. |
| `SITEGUARD_ALLOWED_ORIGINS` | empty | Comma-separated extra origins allowed to send POST/PATCH/DELETE, for a reverse proxy that rewrites `Host`. |
| `SITEGUARD_API_TIMEOUT_MS` | `300000` | Upper bound for one proxied API call (a full AI investigation with a live model can take minutes). |
| `PORT`, `HOSTNAME` | `3000`, `0.0.0.0` | Listen address of `npm start` and the Docker image. |

## Architecture

```text
browser ──same origin──▶ Next.js server (BFF) ──Bearer token──▶ FastAPI (authorizes every call)
          cookie sg_session (httpOnly)        app/api/backend/[...path]
```

### Backend-for-frontend proxy

- `app/api/session/route.ts`: `POST` signs in against `POST /auth/login` and stores the token in the `sg_session`
  cookie (httpOnly, SameSite=Lax, Path=/, 8 hours, Secure when `NODE_ENV=production`). The token is never returned
  to browser JavaScript. `DELETE` signs out.
- `app/api/backend/[...path]/route.ts`: forwards GET/POST/PATCH (JSON and multipart) to `SITEGUARD_API_URL` with
  `Authorization: Bearer <cookie>`. It passes the status, body, `Content-Type`, `Content-Disposition` and
  `X-Correlation-ID` through, and nothing else (no upstream cookies). Only the API roots the app uses are
  reachable; `/auth/*` and the OpenAPI docs are not. When the API answers 401, the cookie is cleared.
- CSRF: every non-GET request to the BFF must carry an `Origin` that matches the `Host` (or is listed in
  `SITEGUARD_ALLOWED_ORIGINS`); anything else gets 403 before the API is called. SameSite=Lax is the second layer.
- `proxy.ts` redirects page requests without a session cookie to `/login?next=...`. It is only a convenience:
  the API validates the token on every call. `next` is accepted only as a same-site path (no open redirects).
- `app/api/health/route.ts` reports the web app's liveness and whether the API is reachable (Docker health check).
- `next.config.ts` sets a Content-Security-Policy (`default-src 'self'`, no framing, `object-src 'none'`),
  `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` and `Permissions-Policy`.

In production, serve the app over HTTPS: the session cookie is Secure, so a browser on plain HTTP (other than
`http://localhost`) will not keep it.

### Authorization in the UI

The browser never decides authorization. `GET /projects` and `GET /incidents/{id}` return a `permissions` array
for the signed-in user; `lib/permissions.ts` uses it only to decide which controls to show (for example the
Approve button needs `APPROVE_CAPA`, or `APPROVE_CRITICAL` for a critical action, and the audit log needs
`VIEW_AUDIT`). The API checks every call again. A 403 renders the "Not authorized" state, a 404 says the record
does not exist or is outside the user's projects (the API does not reveal which), and a 401 sends the user to
sign in.

### Data and screen states

- `lib/api.ts` unwraps the API envelope `{"data": ..., "error": ...}` and throws `ApiError` with the status, error
  code, message and correlation ID. Network failures become `NETWORK_ERROR`.
- `lib/hooks.ts`: `useApi` (load with abort on change, reload, refreshing flag) and `useMutation` (pending, error,
  success message).
- `components/states.tsx`: loading, empty, error, partial result, success and unauthorized states. Every error
  shows the API's message, error code and correlation ID, so support can find the request in the API logs.
- The selected project is remembered per browser in `localStorage` (`siteguard.projectId`); if storage is
  unavailable the first project is used.

### Screens

| Route | What it does |
|---|---|
| `/login` | Sign in through the BFF. |
| `/dashboard` | KPI tiles, incidents by status, severity, domain and month, recurring hazards from AI triage, agent run health, CAPA status, overdue actions, recent incidents. |
| `/incidents` | Incident register with status, severity, domain and text filters. |
| `/incidents/new` | Report an incident (validated in the browser, validated again by the API). |
| `/incidents/[id]` | Command center: reported facts, lifecycle, evidence upload and download with SHA-256, AI investigation with staged progress and labelled agent panels, risk matrix and human risk assessment, CAPA review (approve, modify, reject with a reason), progress, verification, manual status changes, closure with the API's close blockers, timeline. |
| `/review` | CAPA board with the pending review queue and tabs by approval and work status. |
| `/knowledge` | Documents and authorized search with source title, document type, citation ref and the suspicious-content flag. |
| `/audit` | Audit log, shown only with `VIEW_AUDIT`. |

AI output is framed consistently (`components/ai/ai-panel.tsx`): dashed violet border, the "AI decision support,
needs human review" label, provider (a fallback provider is highlighted), confidence (below 50% is marked low),
review flags and reasons, open questions and the evidence it cites. Output with no citations is marked as
unsupported. Reported facts and human decisions use different styling, so AI output is never mistaken for them.

The investigation call is synchronous, so the progress view estimates which agent is running from elapsed time and
then shows the real outcome of each step (succeeded, failed, skipped by triage routing).

### Accessibility

Semantic landmarks and headings, a skip link, labels on every control, visible focus rings, `aria-current` on
navigation and the lifecycle stepper, and keyboard-operable tabs on the review board. Severity and risk are text
badges with a distinct shape per level (circle, diamond, triangle, octagon); status is never shown by colour alone.
Charts print their values and have a screen-reader table.

## Tests

```bash
npm run lint        # ESLint (next core-web-vitals + TypeScript + jsx-a11y rules), no warnings allowed
npm run typecheck   # next typegen && tsc --noEmit
npm test            # Vitest: API client and envelope, permission gating, badges, AI panel labelling,
                    # screen states, BFF origin check, proxy route, session cookie, page redirect
npm run build
```

`make web-test` runs all four. Tests live in `tests/`; BFF route tests run in the Node environment, component
tests in jsdom. None of them needs the API.

### Browser E2E

`e2e/incident-flow.spec.ts` drives the real stack: the HSE manager signs in, reports an incident, uploads a text
evidence file, runs the AI investigation, checks the labelled AI panels and approves a proposed action with a
reason; then the auditor signs in and sees the same incident read-only, with no Approve, Run AI investigation or
Upload evidence controls, and the unauthorized state on the report form.

```bash
make run                                   # API with demo data on :8000
cd frontend && npm run build && npm start  # web app on :3000
npx playwright install chromium            # once
npm run e2e                                # or: make web-e2e
```

| Variable | Default | Purpose |
|---|---|---|
| `E2E_WEB_URL` | `http://localhost:3000` | Web app under test. |
| `E2E_PASSWORD` | `siteguard-demo` | Demo account password. |
| `PW_CHROMIUM_PATH` | unset | Use a preinstalled Chromium instead of the one `playwright install` downloads. |

The test creates a new incident on each run, so it can run repeatedly against the same database. CI runs it
against a fresh SQLite database with the offline rules provider (`.github/workflows/ci.yml`, job `e2e`).

## Known limitations

- Investigation progress is estimated while the request runs; the API returns all agent results at once.
- Investigation `flags` from the run response are shown right after a run but are not stored by the API, so they
  are not shown after a reload (the per-agent review reasons are).
- People outside the incident's project (for example organization-level reviewers in the audit log) show as user
  IDs, because member names come from `GET /projects/{id}/members`.
- Citations to knowledge chunks show the document title when the compliance agent reported it; otherwise a short
  chunk ID (there is no chunk lookup endpoint).
