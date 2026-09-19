import random
import uuid
from datetime import date, timedelta

from locust import HttpUser, between, task

CITIES = ["Moscow", "Saint Petersburg", "Kazan", "Sochi", "Kaliningrad"]
BASE_DAY = date(2027, 1, 1)


def random_stay() -> tuple[str, str]:
    start = BASE_DAY + timedelta(days=random.randint(0, 700))
    return start.isoformat(), (start + timedelta(days=random.randint(1, 4))).isoformat()


class Guest(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self):
        self.user_id = f"guest-{uuid.uuid4().hex[:12]}"
        self.headers = {"x-user-id": self.user_id}
        self.offers: list[tuple[int, str, str]] = []

    @task(6)
    def search(self):
        check_in, check_out = random_stay()
        params = {"city": random.choice(CITIES), "check_in": check_in, "check_out": check_out,
                  "guests": random.choice([1, 2, 2, 3, 4])}
        with self.client.get("/catalog/search", params=params, headers=self.headers,
                             name="/catalog/search", catch_response=True) as r:
            if r.status_code == 429:
                r.success()
                return
            if r.status_code != 200:
                r.failure(f"status {r.status_code}")
                return
            rooms = [rid for h in r.json()["hotels"] for o in h["offers"] for rid in o["room_ids"]]
            if rooms:
                self.offers = [(random.choice(rooms), check_in, check_out)]

    @task(2)
    def book_and_pay(self):
        if self.offers:
            room_id, check_in, check_out = self.offers.pop()
        else:
            room_id, (check_in, check_out) = random.randint(1, 500), random_stay()
        with self.client.post("/bookings", json={"room_id": room_id, "check_in": check_in, "check_out": check_out},
                              headers={**self.headers, "idempotency-key": uuid.uuid4().hex},
                              name="/bookings", catch_response=True) as r:
            if r.status_code == 429:
                r.success()
                return
            if r.status_code != 202:
                r.failure(f"status {r.status_code}")
                return
            booking = r.json()
        with self.client.post("/payments",
                              json={"booking_id": booking["booking_id"], "amount_minor": booking["amount_minor"]},
                              headers={**self.headers, "idempotency-key": uuid.uuid4().hex},
                              name="/payments", catch_response=True) as r:
            if r.status_code in (200, 402, 429):
                r.success()
            else:
                r.failure(f"status {r.status_code}")

    @task(1)
    def my_bookings(self):
        self.client.get("/bookings", headers=self.headers, name="/bookings [list]")


class BurstGuest(HttpUser):
    fixed_count = 3
    wait_time = between(0.05, 0.1)
    fixed_user = "burst-guest"

    @task
    def hammer_search(self):
        check_in, check_out = random_stay()
        with self.client.get("/catalog/search",
                             params={"city": "Sochi", "check_in": check_in, "check_out": check_out},
                             headers={"x-user-id": self.fixed_user}, name="/catalog/search [burst]",
                             catch_response=True) as r:
            if r.status_code in (200, 429):
                r.success()

