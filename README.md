# shop-finder-api

Backend for a "where can I buy this nearby?" app. Shop owners publish prices and stock,
shoppers search for a product around their location and get the nearest shops that have it,
cheapest first.

Built with Django and Django REST Framework on two databases: PostgreSQL for users, shops
and offers, MongoDB for the product catalogue and search statistics. Feed imports run in a
Celery worker with Redis as the broker. Everything runs locally with Docker Compose.

## Stack

| Part | Used for |
|---|---|
| Django 6.1, DRF 3.18 | API, admin, auth |
| PostgreSQL 18 | users, shops, offers, import history (constraints, transactions) |
| MongoDB 8.0 (PyMongo) | catalogue with per-category attributes, text search, search events |
| Celery 5.7 + Redis 8 | background feed imports with retries; Redis also holds the cache |
| simplejwt | JWT access and refresh tokens |
| drf-spectacular | OpenAPI schema and Swagger UI |
| pytest, factory-boy, ruff | tests and linting; GitHub Actions runs them on every push |

## Run it with Docker Compose

You need Docker with the Compose plugin. All ports are published on 127.0.0.1 only.

```bash
python3 scripts/make_env.py
docker compose up -d --build
docker compose exec api python manage.py seed_demo
```

`make_env.py` writes `.env` with a random secret key and database password (`.env` is in
`.gitignore`). `seed_demo` loads synthetic shops around central Kyiv, 24 products, offers
and some searches, and prints the password of the demo shop owner `demo-owner`.

| Service | Address on your machine |
|---|---|
| API and Swagger UI | http://127.0.0.1:8020/api/v1/docs/ |
| Django admin | http://127.0.0.1:8020/admin/ (create a user with `docker compose exec api python manage.py createsuperuser`) |
| PostgreSQL | 127.0.0.1:5435 |
| MongoDB | 127.0.0.1:27018 |
| Redis | 127.0.0.1:6380 |

Check that everything is connected:

```bash
docker compose exec api python manage.py doctor
```

Stop with `docker compose down`; add `-v` to delete the database volumes too.

## Try the API

Search for oat milk within 2 km of Maidan Nezalezhnosti:

```bash
curl "http://127.0.0.1:8020/api/v1/search/?q=oat+milk&lat=50.4501&lon=30.5234&radius_km=2"
```

Log in as the demo owner (use the password `seed_demo` printed) and keep the token:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8020/api/v1/auth/token/ -H "Content-Type: application/json" -d '{"username": "demo-owner", "password": "PASTE-PASSWORD"}' | python3 -c "import json, sys; print(json.load(sys.stdin)['access'])")
```

Upload a price list to a demo shop; a Celery worker applies it. On a fresh database the
first demo shop has id 1 (`GET shops/mine/` with the token lists them):

```bash
curl -X POST http://127.0.0.1:8020/api/v1/shops/1/imports/ -H "Authorization: Bearer $TOKEN" -F "file=@examples/prices.csv;type=text/csv"
```

See the result, including the row that was rejected:

```bash
curl http://127.0.0.1:8020/api/v1/shops/1/imports/ -H "Authorization: Bearer $TOKEN"
```

What do people nearby search for and not find?

```bash
curl "http://127.0.0.1:8020/api/v1/stats/most-wanted/?lat=50.4501&lon=30.5234&unmet=true" -H "Authorization: Bearer $TOKEN"
```

## Endpoints

All under `/api/v1/`. The full schema is at `/api/v1/schema/`.

| Endpoint | Who | What |
|---|---|---|
| `GET search/?q=&lat=&lon=&radius_km=` | anyone | offers in stock nearby: nearest shop first, then cheapest; filters `category`, `attr.<name>`, `max_price` |
| `GET shops/?lat=&lon=&radius_km=` | anyone | shops nearby with their distance; `q` filters by name |
| `POST shops/` | logged in | open a shop; the creator owns it |
| `PATCH`, `DELETE shops/{id}/` | owner | edit or close a shop (closing hides it, nothing is deleted) |
| `GET shops/mine/` | logged in | your shops, closed ones included |
| `GET shops/{id}/offers/` | anyone | the shop's prices, cheapest first |
| `PUT`, `DELETE shops/{id}/offers/{product_id}/` | owner | set or remove the price and stock of one product |
| `POST shops/{id}/imports/` | owner | load a CSV or JSON feed by `url` or `file` (202, processed in the background) |
| `GET shops/{id}/imports/`, `imports/{id}/` | owner | import history with per-row errors |
| `GET products/?q=&category=&attr.<name>=` | anyone | catalogue search; every word must match |
| `POST products/`, `PATCH`, `DELETE products/{id}/` | staff | maintain the catalogue (delete archives) |
| `GET stats/most-wanted/?lat=&lon=` | logged in | top searches nearby; `unmet=true` for the ones that found nothing |
| `POST auth/register/`, `auth/token/`, `auth/token/refresh/` | anyone | sign up and get JWT tokens |
| `GET health/` | anyone | 200 when PostgreSQL, MongoDB and Redis answer, otherwise 503 |

A feed has the columns `barcode`, `price` and `quantity`. CSV may use `,` or `;` and a
decimal comma, as spreadsheet exports in Ukraine do; JSON is a list of rows or
`{"items": [...]}`. Bad rows are reported by line number and skipped.

## Running on a server

`compose.prod.yaml` holds the settings for a small server (2 GB of memory), and
`make_env.py --host` writes the production values: debug off, the public host name, secure
cookies, one gunicorn process with threads.

```bash
python3 scripts/make_env.py --host shop.example.com
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
```

The API still listens on 127.0.0.1:8020 only, so it needs an HTTPS proxy on the same
machine. [portfolio-server](https://github.com/lecorrr/portfolio-server) sets up an AWS EC2
instance this way, with Caddy in front of this project and its sibling.

## Developing without rebuilding the image

Run the databases in Compose and Django from a virtual environment (Python 3.12 or newer):

```bash
docker compose up -d postgres mongo redis
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.lock
.venv/bin/python manage.py migrate
.venv/bin/python manage.py ensure_mongo
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

The worker, in a second terminal:

```bash
.venv/bin/celery -A shopfinder worker --loglevel=INFO
```

## Tests

The tests use the real PostgreSQL and MongoDB from Compose, in separate test databases
(`test_shopfinder` and `shopfinder_test`), so start those first:

```bash
docker compose up -d postgres mongo redis
.venv/bin/pytest
```

Before pushing, run what CI runs:

```bash
.venv/bin/ruff format --check . && .venv/bin/ruff check . && .venv/bin/python manage.py makemigrations --check --dry-run && .venv/bin/pytest
```

## Configuration

Settings come from environment variables (or `.env`, see `.env.example`).

| Variable | Default | Meaning |
|---|---|---|
| `DJANGO_SECRET_KEY` | required | signing key for sessions and JWT |
| `DJANGO_DEBUG` | `false` | never `true` on a public server |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | host names the API answers to |
| `DATABASE_URL` | required | PostgreSQL URL |
| `MONGO_URL`, `MONGO_DB` | required, `shopfinder` | MongoDB server and database |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Celery broker |
| `CACHE_URL` | in-process memory | use Redis when there is more than one process |
| `SEARCH_EVENTS_KEEP_DAYS` | `180` | search statistics older than this are deleted by MongoDB |
| `THROTTLE_ANON`, `THROTTLE_USER`, `THROTTLE_REGISTER`, `THROTTLE_IMPORTS` | `60/min`, `240/min`, `10/hour`, `30/hour` | request limits |
| `WEB_CONCURRENCY` | `1` | gunicorn worker processes |

## Layout

```
shopfinder/   settings, URLs, Celery app, the MongoDB client
accounts/     user model, registration, JWT login
shops/        shops, distance maths, nearby query
catalog/      products in MongoDB: repository, attributes per category, barcodes
offers/       price and stock per shop and product, the combined search
imports/      feed parsing, safe download, the import service and Celery task
stats/        search events in MongoDB and the "most wanted" aggregation
core/         pagination, health checks, management commands
tests/        pytest suite, one file per area
```

How the parts fit together, and why there are two databases, is in
[ARCHITECTURE.md](ARCHITECTURE.md).

## Updating dependencies

`requirements.lock` (image) and `requirements-dev.lock` (development and CI) pin exact
versions. After changing `pyproject.toml`, regenerate them with
[uv](https://docs.astral.sh/uv/):

```bash
uv pip compile pyproject.toml --python-version 3.14 -o requirements.lock
uv pip compile pyproject.toml --extra dev --python-version 3.14 -o requirements-dev.lock
```
