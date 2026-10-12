# CapitalFlow — Assessment Notes

Submission for Digital Alpha Full Stack Intern Assessment: Bank Reconciliation for Capital Calls.

App Name: **CapitalFlow**

---

## Setup and Running

### Option 1: Docker (Recommended)
Prerequisites: Docker with Docker Compose.

```bash
docker compose up --build
```
- Web Application: http://localhost:5173
- Backend API Health: http://localhost:8000/api/health/

### Option 2: Local Setup
Prerequisites: Python 3.12+, Node.js 20+, PostgreSQL 14+.

```bash
# 1. Database
createdb capitalflow

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 0.0.0.0:8000

# 3. Frontend (in another terminal)
cd frontend
cp .env.example .env
npm install
npm run dev
```

---

## Running Tests

Single command to run the backend test suite:

```bash
# With Docker:
docker compose exec backend python manage.py test reconciliation

# Or locally:
cd backend && python manage.py test reconciliation
```

---

## Data Model & API Endpoints

### Models
- **Organization**: Tenant entity (`northwind`, `bluebird`). All business records link to an organization.
- **InvestorEntity**: Legal investor entity name (e.g., "Patel Family Trust").
- **CapitalCall**: Call number, call date, due date.
- **LineItem**: Expected wire reference (e.g. `CC-1003`), amount called, amount funded, remaining amount, status (`open`, `partially_funded`, `funded`).
- **BankTransaction**: Imported CSV transaction row with bank reference, date, type (`credit`/`debit`), amount (Decimal), and status (`suggested`, `needs_review`, `reconciled`, `ignored`).
- **ReconciliationMatch**: Link between a bank transaction and line item, with match reason and status (`proposed`, `approved`, `rejected`).

### REST API Endpoints
All business endpoints require the `X-Organization` header (e.g. `X-Organization: northwind`).

- `GET /api/health/` — Health check (no header required).
- `GET /api/organizations/` — List organizations for switcher (no header required).
- `POST /api/imports/` — Upload statement CSV (`multipart/form-data`).
- `GET /api/transactions/` — List transactions for organization (newest first) with suggestions & reasons.
- `GET /api/line-items/` — List capital call line items and funding progress.
- `POST /api/matches/<id>/approve/` — Atomically approve a proposed match and update line item funding.
- `POST /api/matches/<id>/reject/` — Reject a proposed match.
- `POST /api/transactions/<id>/ignore/` — Mark a transaction ignored and reject any proposed matches.

---

## Assumptions & Trade-offs

1. **Currency & Precision**: Standard 2-decimal precision used throughout. All currency values are strictly handled as `Decimal` in Python and numeric strings in TypeScript/JSON to avoid floating-point rounding issues.
2. **Organization Scoping**: Scoping is handled by inspecting the `X-Organization` request header on API requests. Missing header returns 400, unknown organization or cross-tenant query returns 404.
3. **Matching Rules**: 
   - Matching runs on imported credit transactions against eligible open line items whose call date is on or before the transaction date.
   - Reference matching takes priority (checks normalized wire reference against transaction description or bank reference).
   - If no reference matches, it checks exact amount equality combined with normalized investor name matching.
4. **Concurrency & Safe Approvals**: The approval action uses `select_for_update()` inside a database transaction (`transaction.atomic`) to ensure concurrent requests cannot double-fund a line item or exceed the called amount (returns 409 Conflict if already reconciled or over remaining).
5. **Debits**: Stored with status `ignored` as specified; debits are not matched against capital calls.

---

> I completed this assessment without using AI assistance.
