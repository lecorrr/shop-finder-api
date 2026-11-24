"""The product catalogue in MongoDB, behind one class so views never touch PyMongo."""

import re
from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import CollectionInvalid, DuplicateKeyError

from catalog.attributes import CATEGORIES
from shopfinder import mongo

COLLECTION = "products"
TEXT_INDEX = "product_text"
BARCODE_INDEX = "product_barcode_unique"
CATEGORY_INDEX = "product_category"
INDEX_NAMES = (TEXT_INDEX, BARCODE_INDEX, CATEGORY_INDEX)
ACTIVE = "active"
ARCHIVED = "archived"
MAX_SEARCH_TERMS = 5
# Ukrainian words can contain an apostrophe, typed as ' or as U+2019.
_WORD = re.compile(r"[\w'\u2019-]+")

PRODUCT_SCHEMA = {
    "bsonType": "object",
    "required": ["name", "category", "attributes", "tags", "status", "created_at", "updated_at"],
    "properties": {
        "name": {"bsonType": "string", "minLength": 1, "maxLength": 200},
        "brand": {"bsonType": "string", "maxLength": 100},
        "category": {"enum": CATEGORIES},
        "barcode": {"bsonType": "string", "pattern": "^[0-9]{13}$"},
        "attributes": {"bsonType": "object"},
        "tags": {"bsonType": "array", "items": {"bsonType": "string"}},
        "status": {"enum": [ACTIVE, ARCHIVED]},
        "created_at": {"bsonType": "date"},
        "updated_at": {"bsonType": "date"},
    },
}


class DuplicateBarcode(Exception):
    pass


def ensure_schema(db: Database) -> None:
    """Create or update the collection's validator and indexes. Safe to run again."""
    try:
        db.create_collection(COLLECTION, validator={"$jsonSchema": PRODUCT_SCHEMA})
    except CollectionInvalid:
        db.command("collMod", COLLECTION, validator={"$jsonSchema": PRODUCT_SCHEMA})
    products = db[COLLECTION]
    # "none": MongoDB has no Ukrainian stemmer, so words match as written (case-insensitive).
    products.create_index(
        [("name", "text"), ("brand", "text"), ("tags", "text")],
        name=TEXT_INDEX,
        default_language="none",
        weights={"name": 5, "brand": 3, "tags": 2},
    )
    products.create_index(
        [("barcode", ASCENDING)],
        name=BARCODE_INDEX,
        unique=True,
        partialFilterExpression={"barcode": {"$type": "string"}},
    )
    products.create_index([("category", ASCENDING), ("status", ASCENDING)], name=CATEGORY_INDEX)


def parse_id(product_id: str) -> ObjectId | None:
    try:
        return ObjectId(product_id)
    except (InvalidId, TypeError):
        return None


def text_query(text: str) -> str | None:
    """Every word must match: MongoDB ORs bare words, so each one is quoted."""
    words = _WORD.findall(text.lower())[:MAX_SEARCH_TERMS]
    return " ".join(f'"{word}"' for word in words) or None


def to_api(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "name": document["name"],
        "brand": document.get("brand", ""),
        "category": document["category"],
        "barcode": document.get("barcode"),
        "attributes": document.get("attributes", {}),
        "tags": document.get("tags", []),
        "status": document["status"],
        "created_at": document["created_at"],
        "updated_at": document["updated_at"],
    }


class ProductRepository:
    def __init__(self, db: Database) -> None:
        self.products: Collection = db[COLLECTION]

    def create(self, data: dict) -> dict:
        now = datetime.now(UTC)
        document = {**_without_empty_barcode(data), "status": ACTIVE, "created_at": now}
        document["updated_at"] = now
        try:
            result = self.products.insert_one(document)
        except DuplicateKeyError as error:
            raise DuplicateBarcode(data.get("barcode")) from error
        return {**document, "_id": result.inserted_id}

    def get(self, product_id: str) -> dict | None:
        object_id = parse_id(product_id)
        return None if object_id is None else self.products.find_one({"_id": object_id})

    def get_many(self, product_ids: list[str]) -> dict[str, dict]:
        object_ids = [oid for oid in map(parse_id, product_ids) if oid is not None]
        return {str(doc["_id"]): doc for doc in self.products.find({"_id": {"$in": object_ids}})}

    def update(self, product_id: str, changes: dict) -> dict | None:
        object_id = parse_id(product_id)
        if object_id is None:
            return None
        update: dict = {"$set": {**changes, "updated_at": datetime.now(UTC)}}
        if "barcode" in changes and not changes["barcode"]:
            update["$set"].pop("barcode")
            update["$unset"] = {"barcode": ""}
        try:
            return self.products.find_one_and_update(
                {"_id": object_id}, update, return_document=ReturnDocument.AFTER
            )
        except DuplicateKeyError as error:
            raise DuplicateBarcode(changes.get("barcode")) from error

    def archive(self, product_id: str) -> bool:
        updated = self.update(product_id, {"status": ARCHIVED})
        return updated is not None

    def ids_by_barcode(self, barcodes: list[str]) -> dict[str, str]:
        found = self.products.find({"barcode": {"$in": barcodes}, "status": ACTIVE}, {"barcode": 1})
        return {doc["barcode"]: str(doc["_id"]) for doc in found}

    def search(
        self,
        *,
        text: str | None = None,
        category: str | None = None,
        attributes: dict | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Active products matching all the given conditions, best text match first."""
        query: dict = {"status": ACTIVE}
        if category:
            query["category"] = category
        for name, value in (attributes or {}).items():
            query[f"attributes.{name}"] = value
        if text and (words := text_query(text)):
            query["$text"] = {"$search": words}
            cursor = self.products.find(query, {"score": {"$meta": "textScore"}}).sort(
                [("score", {"$meta": "textScore"}), ("_id", ASCENDING)]
            )
        else:
            cursor = self.products.find(query).sort([("name", ASCENDING), ("_id", ASCENDING)])
        total = self.products.count_documents(query)
        return list(cursor.skip(offset).limit(limit)), total


def product_repository() -> ProductRepository:
    """The repository on the configured database, for views and tasks."""
    return ProductRepository(mongo.database())


def _without_empty_barcode(data: dict) -> dict:
    # Absent rather than null: the unique index covers only products that have a barcode.
    return {key: value for key, value in data.items() if not (key == "barcode" and not value)}
