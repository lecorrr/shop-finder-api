"""Search events in MongoDB: what people look for near a place, and what they don't find.

Events keep no user and a location rounded to about a kilometre, and a TTL index deletes
them after SEARCH_EVENTS_KEEP_DAYS.
"""

from datetime import UTC, datetime, timedelta

from pymongo import ASCENDING, GEOSPHERE
from pymongo.database import Database
from pymongo.errors import OperationFailure

COLLECTION = "search_events"
LOCATION_INDEX = "event_location"
TTL_INDEX = "event_ttl"
INDEX_NAMES = (LOCATION_INDEX, TTL_INDEX)
# Two decimals of a degree is about 1.1 km north-south: enough for "near", not for a home.
LOCATION_DECIMALS = 2
INDEX_OPTIONS_CONFLICT = 85


def ensure_schema(db: Database, keep_days: int) -> None:
    events = db[COLLECTION]
    events.create_index([("location", GEOSPHERE)], name=LOCATION_INDEX)
    seconds = keep_days * 24 * 3600
    try:
        events.create_index([("created_at", ASCENDING)], name=TTL_INDEX, expireAfterSeconds=seconds)
    except OperationFailure as error:
        if error.code != INDEX_OPTIONS_CONFLICT:
            raise
        # The retention period changed: update the existing index in place.
        db.command("collMod", COLLECTION, index={"name": TTL_INDEX, "expireAfterSeconds": seconds})


def normalize_query(text: str) -> str:
    return " ".join(text.lower().split())[:100]


class SearchEventRepository:
    def __init__(self, db: Database) -> None:
        self.events = db[COLLECTION]

    def log(
        self,
        *,
        q: str,
        category: str | None,
        lat: float,
        lon: float,
        radius_km: float,
        results: int,
        now: datetime | None = None,
    ) -> None:
        self.events.insert_one(
            {
                "q": normalize_query(q),
                "category": category,
                "location": {
                    "type": "Point",
                    "coordinates": [round(lon, LOCATION_DECIMALS), round(lat, LOCATION_DECIMALS)],
                },
                "radius_km": radius_km,
                "results": results,
                "created_at": now or datetime.now(UTC),
            }
        )

    def most_wanted(
        self,
        *,
        lat: float,
        lon: float,
        radius_km: float,
        days: int,
        limit: int = 10,
        unmet_only: bool = False,
        now: datetime | None = None,
    ) -> list[dict]:
        """The most searched queries near a point, with how many of them found nothing."""
        match: dict = {"created_at": {"$gte": (now or datetime.now(UTC)) - timedelta(days=days)}}
        if unmet_only:
            match["results"] = 0
        pipeline = [
            {
                "$geoNear": {
                    "near": {"type": "Point", "coordinates": [lon, lat]},
                    "distanceField": "distance_m",
                    "maxDistance": radius_km * 1000,
                    "query": match,
                    "spherical": True,
                }
            },
            {
                "$group": {
                    "_id": "$q",
                    "searches": {"$sum": 1},
                    "unmet": {"$sum": {"$cond": [{"$eq": ["$results", 0]}, 1, 0]}},
                    "last_searched": {"$max": "$created_at"},
                }
            },
            {"$sort": {"searches": -1, "_id": 1}},
            {"$limit": limit},
        ]
        return [
            {
                "query": row["_id"],
                "searches": row["searches"],
                "unmet": row["unmet"],
                "last_searched": row["last_searched"],
            }
            for row in self.events.aggregate(pipeline)
        ]
