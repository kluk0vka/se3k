import random
import uuid

from locust import HttpUser, between, task


class Guest(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        self.user_id = str(uuid.uuid4())

    @task(5)
    def search(self):
        self.client.get(
            "/catalog/search",
            params={"city": random.choice(["Moscow", "Kazan", "Sochi"]), "guests": 2},
            headers={"x-user-id": self.user_id},
            name="/catalog/search",
        )

    @task(1)
    def book(self):
        self.client.post(
            "/bookings",
            json={"room_id": random.randint(1, 500), "check_in": "2026-10-01", "check_out": "2026-10-03"},
            headers={"x-user-id": self.user_id},
            name="/bookings",
        )
