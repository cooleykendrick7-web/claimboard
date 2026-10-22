# ClaimBoard — Ken's live claims dashboard

Real database-backed dashboard for Ken's claims: 10 state unclaimed-property
claims + no-proof settlement claims found by the daily Claim Finder sweep.

- Live totals computed from SQLite on every request (paid / pipeline / confirmed / found).
- Owner login (CLAIMBOARD_OWNER_PASSWORD) unlocks "Yes — that's me" / "Not mine"
  buttons on found settlements: Ken's confirmation is what queues a claim for filing.
- Admin API (X-Admin-Key = owner password) lets the daily sweep add new finds
  and lets filing work update statuses / record payments.
- PWA: manifest + service worker (shell-only caching; data always live),
  apple-touch-icon — installs to the home screen full-screen like an app.
- No personal identifiers are stored — claim names, amounts, deadlines, statuses only.

Run locally: `uvicorn app:app --port 8000` with CLAIMBOARD_OWNER_PASSWORD set.
Deploy: GitHub repo → Render Blueprint (render.yaml, Starter + 1GB disk at /data).
