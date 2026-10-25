# Nexus

Nexus uses the canonical FastAPI runtime in `nexus_services/nexus_api_server.py`.

## Local startup

1. Install the Python dependencies from `requirements.txt`.
2. Copy `.env.example` to `.env` and configure secrets through your environment or secret manager. Never commit credentials.
3. Set a strong `NEXUS_API_BEARER_TOKEN` before using functional API routes.
4. Start the runtime with `./start_nexus.sh` or `uvicorn nexus_services.nexus_api_server:app --host 0.0.0.0 --port 8000`.

The unauthenticated `/health` route is liveness-only. Functional routes are locked when the bearer token is missing or invalid.

## Persistent storage

The operational journal, conversation memory, payout ledger, and task repositories use SQLite-backed storage. Set `NEXUS_OPERATIONAL_DB_PATH` to a file path on a durable volume. Nexus creates the parent directory if needed. The shared connection layer configures WAL, full synchronous commits, foreign keys, and a bounded busy timeout. The canonical task repository maintains versioned migrations and uses its own `canonical_tasks` table to avoid colliding with the legacy task table.

SQLite is durable embedded storage, not a horizontally scalable shared database. It is appropriate for a single-node deployment with moderate write concurrency. For multiple application instances or high sustained write volume, implement and configure a PostgreSQL repository backend before scaling out. A SQLite file checked into Git would not be a runtime database and is intentionally not included.

## Financial architecture

Nexus does **not** own a wallet, hold user funds, or generate blockchain private keys. Platform accounts remain separate and authoritative at their respective providers. Nexus records timestamped, evidence-linked balance snapshots in a consolidated view; those snapshots are external platform balances, not assets held by Nexus.

The payout destination is the user's external prepaid Visa card. Nexus stores only a masked label and, when supplied, the last four digits. It never stores the full card number, CVV/CVC, or issuer credentials. The card is a destination, not a Nexus wallet. Actual payouts require the relevant platform's supported payout flow and external confirmation; recording a payout request is not proof that funds arrived. The ledger does not itself move money, and stablecoin transfers/treasury withdrawals remain disabled.

## Validation

The GitHub Actions workflow runs runtime, browser-safety, operational-journal, memory, financial-boundary, and SQLite persistence regression tests. Changes remain on the feature branch until reviewed and merged.
