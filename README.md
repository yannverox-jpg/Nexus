# Nexus

Nexus uses the canonical FastAPI runtime in `nexus_services/nexus_api_server.py`.

## Local startup

1. Install the Python dependencies from `requirements.txt`.
2. Copy `.env.example` to `.env` and configure secrets through your environment or secret manager. Never commit credentials.
3. Set a strong `NEXUS_API_BEARER_TOKEN` before using functional API routes.
4. Start the runtime with `./start_nexus.sh` or `uvicorn nexus_services.nexus_api_server:app --host 0.0.0.0 --port 8000`.

The unauthenticated `/health` route is liveness-only. Functional routes are locked when the bearer token is missing or invalid.

## Identity, chat, and memory

The canonical API exposes `/api/v1/identity`, `/api/v1/capabilities`, and `/api/v1/providers` so the command center can show what Nexus is configured to do rather than claiming 100% readiness. Open `/dashboard` for the authenticated identity panel and chat with GPT, Gemini, or Claude through their official API connectors. Provider keys are never embedded in the browser. A configured API key means only that a key is present; the status endpoint does not claim the provider has authenticated successfully until a real request succeeds. Nexus reports internal planning readiness separately from external platform execution readiness.

The provider roles are intentionally distinct: GPT reviews reasoning and contradictions; Gemini researches evidence and provenance; Claude reviews architecture, workflows, and e-commerce design. All three are advisors, not an authorization mechanism. Their answers are persisted in SQLite with common secret patterns redacted. Long-term project facts and constraints can be explicitly saved in the memory panel and are included as context in later chats; they cannot override security rules. The configured operational database is shared by the canonical task journal, chat memory, long-term project facts, and payout ledger. Legacy analytics tables use the separate `NEXUS_LEGACY_DB_PATH` to prevent schema collisions. File-backed storage alone does not prove that the hosting provider preserves it across redeploys; set `NEXUS_STORAGE_DURABLE=true` only after confirming the path is on a persistent volume.

Nexus has three built-in safe executors for capability assessment, workflow planning, and reconciliation of saved external-platform balance snapshots. Unsupported work fails closed until a real integration executor is configured. This is readiness for internal planning, not a claim that every platform can already be controlled.

## Browser automation and network settings

Nexus uses the existing nexus_services/stealth_browser_agent.py compatibility module as a policy-aware Playwright browser agent; despite the historical filename, it does not implement stealth or anti-bot evasion. Navigation is limited to NEXUS_BROWSER_ALLOWED_HOSTS. The optional NEXUS_BROWSER_PROXY selects one configured HTTP, HTTPS, or SOCKS5 proxy for authorized privacy and test workflows. Store proxy credentials in NEXUS_BROWSER_PROXY_USERNAME and NEXUS_BROWSER_PROXY_PASSWORD, never in the URL or source code. There is no proxy rotation.

Browser locale and timezone can be set with NEXUS_BROWSER_LOCALE and NEXUS_BROWSER_TIMEZONE. Geolocation emulation is off by default and requires NEXUS_BROWSER_ALLOW_GEOLOCATION=true plus valid latitude/longitude environment variables. These settings are for authorized testing or workflows where location simulation is permitted; they do not change the public IP address.

The browser detects common CAPTCHA and anti-bot challenge indicators and pauses automation with HUMAN_INTERVENTION_REQUIRED. It does not solve CAPTCHA challenges, evade access controls, spoof browser fingerprints, submit forms, log in, or make payments. Sensitive fields and form submissions remain human-controlled. httpx is available for API clients that need explicit timeouts and network configuration; API integrations must honor each provider's terms and rate limits.

## Code adaptation

When `NEXUS_GITHUB_REPOSITORY` and `NEXUS_GITHUB_TOKEN` are configured, the dashboard can submit a complete proposed file to `/api/v1/code-change/proposals`. Nexus creates a separate branch and draft pull request; GitHub Actions runs checks and a human must review and merge. The running production process is never self-edited and Nexus cannot merge its own changes. The token needs repository contents read/write and pull-request write permissions; keep it in the server secret store, never in the browser or repository.

## Persistent storage

The operational journal, conversation memory, payout ledger, and task repositories use SQLite-backed storage. Set `NEXUS_OPERATIONAL_DB_PATH` to a file path on a durable volume. Nexus creates the parent directory if needed. The shared connection layer configures WAL, full synchronous commits, foreign keys, and a bounded busy timeout. The canonical task repository maintains versioned migrations and uses its own `canonical_tasks` table to avoid colliding with the legacy task table.

SQLite is durable embedded storage, not a horizontally scalable shared database. It is appropriate for a single-node deployment with moderate write concurrency. For multiple application instances or high sustained write volume, implement and configure a PostgreSQL repository backend before scaling out. A SQLite file checked into Git would not be a runtime database and is intentionally not included.

## Financial architecture

Nexus does **not** own a wallet, hold user funds, or generate blockchain private keys. Platform accounts remain separate and authoritative at their respective providers. Nexus records timestamped, evidence-linked balance snapshots in a consolidated view; those snapshots are external platform balances, not assets held by Nexus.

The payout destination is the user's external prepaid Visa card. Nexus stores only a masked label and, when supplied, the last four digits. It never stores the full card number, CVV/CVC, or issuer credentials. The card is a destination, not a Nexus wallet. Actual payouts require the relevant platform's supported payout flow and external confirmation; recording a payout request is not proof that funds arrived. The ledger does not itself move money, and stablecoin transfers/treasury withdrawals remain disabled.

## Validation

The GitHub Actions workflow runs runtime, browser-safety, operational-journal, memory, financial-boundary, and SQLite persistence regression tests. Changes remain on the feature branch until reviewed and merged.
