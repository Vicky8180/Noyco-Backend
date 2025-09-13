import hashlib, time
from typing import Optional
from api_gateway.database.db import get_database

COLLECTION_NAME = "stripe_idempotency_keys"
TTL_SECONDS = 24 * 3600

db = get_database()

db[COLLECTION_NAME].create_index("key", unique=True)
# expireAt TTL index
if "expireAt_1" not in db[COLLECTION_NAME].index_information():
    db[COLLECTION_NAME].create_index("expireAt", expireAfterSeconds=0)

def generate(scope: str, *parts: str) -> str:
    base = ":".join([scope, *parts])
    return hashlib.sha256(base.encode()).hexdigest()

def is_processed(key: str) -> bool:
    return db[COLLECTION_NAME].find_one({"key": key}) is not None

def mark_processed(key: str):
    db[COLLECTION_NAME].insert_one({"key": key, "expireAt": time.time() + TTL_SECONDS}) 
