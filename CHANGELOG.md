# Changelog

## 0.1.1 (2026-11-25)

- `compose.prod.yaml` with settings for a 2 GB server.
- `scripts/make_env.py --host NAME` writes production settings for that host name.
- The version is defined once, in the package; the OpenAPI schema and `pyproject.toml`
  read it from there.

## 0.1.0 (2026-11-24)

First version.

- Shops with owners, opening hours and soft delete; nearby search by radius.
- Product catalogue in MongoDB with per-category attributes, EAN-13 barcodes, text search
  and a `$jsonSchema` validator on the collection.
- Offers (price and stock per shop and product) in PostgreSQL; `/search/` combines both
  stores: nearest shop first, then cheapest.
- Feed imports (CSV or JSON, by URL or upload) processed by a Celery worker, with retries,
  per-row error reports and protection against requests to internal addresses.
- Anonymous search statistics in MongoDB with a 2dsphere index and a TTL index; "most
  wanted" and "searched but not found nearby" for shop owners.
- JWT authentication, throttling, OpenAPI schema and Swagger UI.
- Docker Compose for local development, GitHub Actions CI, `doctor`, `ensure_mongo` and
  `seed_demo` management commands.
