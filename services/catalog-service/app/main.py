import hashlib
import json
import logging
from contextlib import asynccontextmanager
from datetime import date

import httpx
from fastapi import FastAPI, HTTPException, Query, Response
from motor.motor_asyncio import AsyncIOMotorClient
from prometheus_client import Counter
from pydantic import BaseModel, Field
from valkey.asyncio import Valkey

from app import seed
from app.config import settings
from staybook_common.app import instrument
from staybook_common.kafka import EventProducer
from staybook_common.logging import setup_logging

setup_logging(settings.service_name)
log = logging.getLogger(__name__)

CACHE = Counter("staybook_catalog_search_cache_total", "Search cache lookups", ["result"])
INVENTORY_CALLS = Counter("staybook_catalog_inventory_calls_total", "Calls to inventory-service", ["result"])

mongo = AsyncIOMotorClient(settings.mongo_uri, serverSelectionTimeoutMS=3000)
db = mongo[settings.mongo_db]
cache = Valkey(host=settings.valkey_host, port=settings.valkey_port, password=settings.valkey_password or None,
               socket_timeout=0.5, decode_responses=True)
http = httpx.AsyncClient(base_url=settings.inventory_url, timeout=settings.inventory_timeout_s)
producer = EventProducer(settings.kafka_bootstrap_servers, settings.service_name)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.hotels.create_index([("city", 1), ("room_types.capacity", 1)])
    await db.hotels.create_index("room_types.room_ids")
    if await db.hotels.estimated_document_count() == 0:
        await db.hotels.insert_many(seed.hotels())
        log.info("catalog seeded")
    await producer.start()
    yield
    await producer.stop()
    await http.aclose()
    await cache.aclose()
    mongo.close()


app = FastAPI(title=settings.service_name, lifespan=lifespan)
instrument(app)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(response: Response) -> dict:
    try:
        await db.command("ping")
        await cache.ping()
    except Exception:
        response.status_code = 503
        return {"status": "storage unavailable"}
    return {"status": "ready" if producer.started else "kafka unavailable"}


async def fetch_availability(room_ids: list[int], check_in: date, check_out: date) -> set[int] | None:
    if not room_ids:
        return set()
    try:
        r = await http.get(
            "/inventory/availability",
            params={"room_ids": ",".join(map(str, room_ids)), "check_in": check_in.isoformat(),
                    "check_out": check_out.isoformat()},
        )
        r.raise_for_status()
        INVENTORY_CALLS.labels("ok").inc()
        return set(r.json()["available"])
    except Exception as exc:
        INVENTORY_CALLS.labels("error").inc()
        log.warning(f"inventory unavailable, degraded search: {exc!r}")
        return None


@app.get("/catalog/search")
async def search(
    city: str = Query(..., min_length=2),
    check_in: date = Query(...),
    check_out: date = Query(...),
    guests: int = Query(2, ge=1, le=8),
) -> dict:
    if check_out <= check_in:
        raise HTTPException(422, "check_out must be after check_in")
    key = "search:" + hashlib.sha1(f"{city.lower()}|{check_in}|{check_out}|{guests}".encode()).hexdigest()
    try:
        cached = await cache.get(key)
    except Exception:
        cached = None
    if cached:
        CACHE.labels("hit").inc()
        return json.loads(cached)
    CACHE.labels("miss").inc()
    hotels = await db.hotels.find(
        {"city": {"$regex": f"^{city}$", "$options": "i"}, "room_types.capacity": {"$gte": guests}}
    ).to_list(100)
    candidates = [rid for h in hotels for rt in h["room_types"] if rt["capacity"] >= guests for rid in rt["room_ids"]]
    available = await fetch_availability(candidates, check_in, check_out)
    nights = (check_out - check_in).days
    results = []
    for h in hotels:
        offers = []
        for rt in h["room_types"]:
            if rt["capacity"] < guests:
                continue
            free = rt["room_ids"] if available is None else [r for r in rt["room_ids"] if r in available]
            if free:
                offers.append({"room_type": rt["code"], "name": rt["name"], "capacity": rt["capacity"],
                               "room_ids": free, "total_price_minor": rt["price_per_night_minor"] * nights})
        if offers:
            results.append({"hotel_id": h["_id"], "name": h["name"], "stars": h["stars"], "offers": offers})
    body = {"city": city, "check_in": str(check_in), "check_out": str(check_out), "guests": guests,
            "availability": "confirmed" if available is not None else "pending", "hotels": results}
    try:
        ttl = settings.search_cache_ttl_s if available is not None else settings.degraded_cache_ttl_s
        await cache.set(key, json.dumps(body), ex=ttl)
    except Exception:
        log.warning("cache write failed")
    return body


@app.get("/catalog/hotels/{hotel_id}")
async def hotel(hotel_id: str) -> dict:
    doc = await db.hotels.find_one({"_id": hotel_id})
    if doc is None:
        raise HTTPException(404, "hotel not found")
    doc["hotel_id"] = doc.pop("_id")
    return doc


class PriceUpdate(BaseModel):
    price_per_night_minor: int = Field(gt=0)


@app.put("/catalog/rooms/{room_id}/price")
async def update_price(room_id: int, body: PriceUpdate) -> dict:
    doc = await db.hotels.find_one_and_update(
        {"room_types.room_ids": room_id},
        {"$set": {"room_types.$[rt].price_per_night_minor": body.price_per_night_minor}},
        array_filters=[{"rt.room_ids": room_id}],
    )
    if doc is None:
        raise HTTPException(404, "room not found")
    async for key in cache.scan_iter(match="search:*", count=500):
        await cache.delete(key)
    await producer.publish(
        "catalog.room-updated", "catalog.room-updated", str(room_id),
        {"room_id": room_id, "hotel_id": doc["_id"], "price_per_night_minor": body.price_per_night_minor},
    )
    return {"room_id": room_id, "price_per_night_minor": body.price_per_night_minor}
