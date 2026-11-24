# Architecture

## Overview

```
              HTTP (JSON, JWT)
                    |
            +-------v--------+         +------------------+
            |  Django + DRF  |-------->|   PostgreSQL     |  users, shops, offers,
            |  (gunicorn)    |         |                  |  import history
            +---+--------+---+         +------------------+
                |        |
                |        |             +------------------+
                |        +------------>|   MongoDB        |  products, search events
                |                      +------------------+
                | queue an import             ^
                v                             |
            +--------+    task    +-----------+----+
            | Redis  |----------->| Celery worker  |----> shop's feed URL (https only)
            +--------+            +----------------+
```

The API and the worker are the same code base and the same Docker image, started with a
different command.

## Apps

| App | Owns | May use |
|---|---|---|
| `accounts` | the user model, registration, JWT endpoints | |
| `shops` | shops, distance maths (`geo.py`), the nearby query | `accounts` |
| `catalog` | products in MongoDB (`repository.py`), category attributes, EAN-13 | |
| `offers` | price and stock per shop and product, the combined search | `shops`, `catalog`, `stats` |
| `imports` | feed parsing, safe download, the import service and Celery task | `shops`, `catalog`, `offers` |
| `stats` | search events in MongoDB and their aggregation | |
| `core` | pagination, health checks, management commands | all of the above |

Views never use PyMongo directly: they go through `ProductRepository` and
`SearchEventRepository`, and only `shopfinder/mongo.py` creates a `MongoClient`.
`tests/test_boundaries.py` fails if that changes.

## Why two databases

PostgreSQL holds everything that needs relations, constraints and transactions: a shop
belongs to a user, an offer is unique per shop and product (`UniqueConstraint`), prices are
positive (`CheckConstraint`), and an import replaces many offers in one transaction.

MongoDB holds data whose shape varies or that is written a lot and read in aggregate:

- **Products.** A drink has a volume and maybe an alcohol content, a shoe has a size and a
  colour. In MongoDB each product keeps its own `attributes` object and can be filtered by
  any of them (`?attr.size_eu=42`). The rules still exist: `catalog/attributes.py` checks
  them per category on every write, and a `$jsonSchema` validator on the collection
  refuses documents without the required fields. A text index covers name, brand and tags.
- **Search events.** One small document per search, a 2dsphere index for "near this
  point" and a TTL index that deletes old events. The "most wanted" report is one
  aggregation pipeline (`$geoNear`, `$group`, `$sort`).

The cost is that there is no transaction or foreign key across the two. The code handles it
like this:

- An offer stores the product's ObjectId as a string. The product must exist and be active
  when the offer is written (`offers/services.py`, and the barcode lookup in imports).
- The API archives products instead of deleting them, so an offer does not end up pointing
  at nothing. Archived products drop out of search; a shop's own offer list still shows
  them, marked `archived`, so the owner can clean up.
- Reads join in Python: the matching products come from MongoDB, then one PostgreSQL query
  fetches the page of offers (a shop's offer list does the reverse, with one `$in` query
  for the products on the page). The number of queries does not grow with the number of
  results; there is a test for that.

## The search, step by step

`GET /api/v1/search/?q=oat milk&lat=50.45&lon=30.52&radius_km=2`

1. MongoDB text search finds active products matching every word (each word is sent as a
   quoted phrase, because MongoDB joins bare words with OR). At most 200 products, best
   match first.
2. PostgreSQL finds offers for those products with stock, in active shops, within the
   radius, ordered by distance, then price. A bounding box on the indexed
   `(latitude, longitude)` columns cuts the candidates first; the exact haversine distance
   is then computed in SQL for the rows left.
3. The page is paginated as usual and the search is logged to MongoDB, without the user and
   with the location rounded to about a kilometre. If logging fails, the search still
   answers.

Distances use a sphere with the mean Earth radius, the same in Python and in SQL. The
bounding box is derived from the same sphere, so it can never be smaller than the circle
(a shop inside the radius but outside the box would silently go missing); a test checks it
on many bearings and latitudes.

PostGIS would do the geometry in the database with a spatial index. For one city and a few
thousand shops, two B-tree ranges and a formula are enough and keep the stack simpler.

## Feed imports

A shop owner posts a URL or uploads a file. The API stores a `FeedImport` row and queues a
Celery task after the transaction commits (`transaction.on_commit`), so the worker never
looks for a row that is not there yet.

```
queued -> running -> done | unchanged | failed
```

- **Download.** Only `https://`, no user name or password in the URL, no redirects, at most
  5 MB, 10 seconds. The host must resolve to public addresses only, which blocks requests
  to localhost, the Docker network or the cloud metadata service (SSRF).
- **Parsing.** `imports/feeds.py` is plain Python with no framework imports. It accepts CSV
  with `,` or `;` and decimal commas, or JSON. A bad row (invalid EAN-13, price that is not
  a positive amount with at most two decimals, repeated barcode) is reported by line and
  skipped; only an unreadable feed fails the whole import.
- **Applying.** Known barcodes become offers with one `INSERT ... ON CONFLICT DO UPDATE`
  per thousand rows, inside a transaction. Running the same feed twice gives the same
  result.
- **Unchanged feeds.** The SHA-256 of the content is stored. If a URL returns exactly what
  the last successful import of that URL applied, the import ends as `unchanged`.
- **Retries.** Network errors, timeouts, HTTP 429 and 5xx, and MongoDB errors are retried
  with growing delays (30 s, then 1, 2 and 4 minutes: 5 attempts in total); the reason is
  shown in the import's `error` while it waits. Anything else fails at once with a reason the owner can
  read. An import whose shop was deleted while it waited is skipped. If Redis is down when
  the import is created, it is marked failed instead of staying queued forever.

## Security notes

- JWT access tokens live 30 minutes, refresh tokens 7 days.
- Owners can only change their own shops, offers and imports; another owner's shop answers
  404, not 403, so ids of other shops are not confirmed.
- Throttling: anonymous, per user, registration and import creation have separate limits.
  With more than one process the cache (and so the throttle counters) must be Redis, which
  is how Compose runs it.
- Uploads over 5 MB are refused from the `Content-Length` header before Django reads them.
- Secrets come from the environment; `.env` is never committed or copied into the image.
- The health endpoint names the failing dependency but not the error text.

## Known limits and next steps

- The SSRF check resolves the host before connecting, and httpx resolves it again. A DNS
  server that answers differently the second time could still point the request at a
  private address. Pinning the checked address for the connection would close that.
- MongoDB has no Ukrainian stemmer, so the text index uses `default_language: none`:
  "молоко" does not match "молока". A search engine (OpenSearch) or Atlas Search would.
- The bounding box does not wrap around the 180th meridian.
- Search events are not deduplicated: one person searching ten times counts ten times.
- No PostGIS, no caching of search results, no per-shop opening-hours logic in search.

## Adding things

- **A product category:** add a serializer to `catalog/attributes.py` and an entry in
  `ATTRIBUTES_BY_CATEGORY`; run `manage.py ensure_mongo` so the validator learns the new
  category name.
- **A feed format:** add a reader next to `_csv_records` in `imports/feeds.py` that returns
  `(line, record)` pairs; row checks stay the same.
- **A dependency to check:** add a function to `core/checks.py`; `/health/` and `doctor`
  both pick it up.
