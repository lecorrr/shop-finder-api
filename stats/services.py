import logging

from pymongo.errors import PyMongoError

from shopfinder import mongo
from stats.repository import SearchEventRepository

log = logging.getLogger(__name__)


def record_search(
    *, q: str, category: str | None, lat: float, lon: float, radius_km: float, results: int
) -> None:
    """Statistics are best effort: a MongoDB hiccup must not fail the user's search."""
    try:
        SearchEventRepository(mongo.database()).log(
            q=q, category=category, lat=lat, lon=lon, radius_km=radius_km, results=results
        )
    except PyMongoError as error:
        log.warning("search event not stored: %s", type(error).__name__)
