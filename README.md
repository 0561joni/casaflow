# CasaFlow

A private Django web app for annual real-estate finance tracking, designed to run on Synology via Docker behind a reverse proxy.

## Features

- Single-user authenticated web UI.
- Grouped properties with units, tenants, leases, and effective-date rent history.
- Annual property snapshots with valuations, costs, vacancy loss, and manual rent adjustments.
- Annual loan snapshots with balances, interest, principal, rates, and debt service.
- Portfolio dashboard with value, debt, equity, NOI, cashflow, LTV, net yield, and cash + equity ROI.
- Excel import for the current `Master-Immos.xlsx` workbook structure.
- PDF, Excel, CSV, and database backup exports.

## Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000`.

## Synology Docker

1. Edit `docker-compose.yml`:
   - Set `DJANGO_SECRET_KEY` to a long random value.
   - Set `DJANGO_ALLOWED_HOSTS` to your reverse proxy host.
   - Set `DJANGO_CSRF_TRUSTED_ORIGINS` to `https://your-domain`.
   - Set `SECURE_SSL_REDIRECT=1` once HTTPS through the reverse proxy is working.
2. Start the app:

```bash
docker compose up -d --build
docker compose exec realestate-finance python manage.py migrate
docker compose exec realestate-finance python manage.py createsuperuser
```

3. Point the Synology reverse proxy to container port `8000`.
4. Keep `./data` backed up with Hyper Backup or snapshots. The app also supports on-demand SQLite backup files under `/data/backups`.

## Workbook Import

After logging in, open **Import**, upload `Master-Immos.xlsx`, and choose the year for the imported annual snapshots. The importer maps:

- `Rohdaten` to tenants, units, leases, and initial rent periods.
- `Mieterliste` indirectly through formulas already present in the workbook.
- `Rentabilität` to properties, purchase values, loans, annual loan snapshots, and annual operating costs.

## KPI Definitions

- Annual rent: prorated sum of effective rent periods overlapping the year.
- NOI: annual rent minus vacancy/loss adjustment and operating costs.
- Debt service: interest paid plus principal paid.
- Pre-tax cashflow: NOI minus debt service.
- Cash + equity ROI: pre-tax cashflow plus principal paid divided by owner equity basis.
- LTV: loan-to-value, calculated as closing debt divided by property value.
- Net yield: NOI divided by property value.
- Gross yield: annual cold rent divided by property value.
