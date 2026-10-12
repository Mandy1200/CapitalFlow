# CapitalFlow — Capital Call Reconciliation

A fund administration app for General Partners: import bank statement CSVs, review deterministic match
suggestions against capital call line items, and approve, reject or ignore them with transaction-safe
funding updates and strict organization isolation.

- **Backend:** Python, Django 5.2, Django REST Framework, PostgreSQL
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS
- Design, matching rules, API reference and limitations: [ASSESSMENT_NOTES.md](ASSESSMENT_NOTES.md)

## Option A: Docker

Prerequisites: Docker with Compose.

```bash
docker compose up --build
```

This starts PostgreSQL, runs migrations and `seed_demo`, and serves:

- UI: http://localhost:5173
- API: http://localhost:8000/api/health/

Run the tests inside the backend container:

```bash
docker compose exec backend python manage.py test reconciliation
```

## Option B: Manual setup

Prerequisites: Python 3.12+, Node.js 20+ (22 recommended), PostgreSQL 14+.

```bash
# 1. Database
createdb capitalflow            # or: psql -c "CREATE DATABASE capitalflow;"

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # adjust POSTGRES_* if needed
python manage.py migrate
python manage.py seed_demo      # safe to run repeatedly
python manage.py runserver      # http://localhost:8000

# 3. Frontend (new terminal)
cd frontend
cp .env.example .env
npm install
npm run dev                     # http://localhost:5173
```

The Vite dev server proxies `/api` to Django (`VITE_PROXY_TARGET`), so no CORS setup is needed. To call
the API directly from another origin, set `VITE_API_BASE_URL` to an absolute URL and add the origin to
`CORS_ALLOWED_ORIGINS` in `backend/.env`.

## Tests and build

```bash
cd backend && python manage.py test reconciliation   # needs PostgreSQL (row locks, constraints)
cd frontend && npm run build                          # type-check + production build
```

## Using the app

1. Open http://localhost:5173. Pick **Northwind Ventures** or **Bluebird Capital** in the header.
2. Under **Import bank statement**, choose `sample_bank_statement.csv` (repo root) and click **Upload CSV**.
   The summary shows imported, duplicate and error counts, plus each skipped row's line number and reason.
3. In **Bank transactions**, approve or reject a specific proposed match, or ignore a credit. Ambiguous
   transactions list every candidate; you choose one.
4. **Capital call line items** shows called, funded and remaining amounts as approvals land.

Reset the demo (deletes imported transactions, sets funding back to zero):

```bash
python manage.py seed_demo --reset
```

Example API call:

```bash
curl -H "X-Organization: northwind" -F file=@sample_bank_statement.csv http://localhost:8000/api/imports/
```
