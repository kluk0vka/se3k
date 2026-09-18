import random

CITIES = ["Moscow", "Saint Petersburg", "Kazan", "Sochi", "Kaliningrad"]
ROOM_TYPES = [
    ("DBL", "Double", 2, 550000),
    ("TRP", "Triple", 3, 720000),
    ("FAM", "Family", 4, 890000),
]
HOTELS_PER_CITY = 10
ROOMS_PER_HOTEL = 10


def hotels() -> list[dict]:
    rng = random.Random(42)
    result, room_id = [], 1
    for ci, city in enumerate(CITIES):
        for h in range(HOTELS_PER_CITY):
            room_types = []
            for code, name, capacity, price in ROOM_TYPES:
                count = ROOMS_PER_HOTEL // len(ROOM_TYPES) + (1 if code == "DBL" else 0)
                ids = list(range(room_id, room_id + count))
                room_id += count
                room_types.append({
                    "code": code, "name": name, "capacity": capacity, "room_ids": ids,
                    "price_per_night_minor": int(price * rng.uniform(0.8, 1.4)),
                })
            result.append({
                "_id": f"htl_{ci + 1:02d}{h + 1:02d}",
                "name": f"{city} Hotel {h + 1}",
                "city": city,
                "stars": rng.randint(2, 5),
                "amenities": rng.sample(["wifi", "parking", "spa", "pool", "gym", "breakfast"], 3),
                "room_types": room_types,
            })
    return result
