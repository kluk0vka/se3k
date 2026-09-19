import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = os.environ.get("BASE_URL", "http://192.168.58.100")
CHECK_IN, CHECK_OUT = os.environ.get("CHECK_IN", "2026-11-10"), os.environ.get("CHECK_OUT", "2026-11-12")


def call(method, path, user, body=None, headers=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"content-type": "application/json", "x-user-id": user, **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def wait_status(booking_id, user, expected, timeout=20):
    deadline, status = time.time() + timeout, None
    while time.time() < deadline:
        _, b = call("GET", f"/bookings/{booking_id}", user)
        status = b["status"]
        if status in expected:
            return status
        time.sleep(0.5)
    return status


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
    if not ok:
        sys.exit(1)


def main():
    guest_a, guest_b = f"smoke-a-{uuid.uuid4().hex[:6]}", f"smoke-b-{uuid.uuid4().hex[:6]}"
    q = urllib.parse.urlencode({"city": "Kazan", "check_in": CHECK_IN, "check_out": CHECK_OUT, "guests": 2})
    code, res = call("GET", f"/catalog/search?{q}", guest_a)
    check("search", code == 200 and res["hotels"], f"hotels={len(res.get('hotels', []))} availability={res.get('availability')}")
    offer = res["hotels"][0]["offers"][0]
    room_id, price = offer["room_ids"][0], offer["total_price_minor"]

    code, b = call("POST", "/bookings", guest_a, {"room_id": room_id, "check_in": CHECK_IN, "check_out": CHECK_OUT},
                   {"idempotency-key": uuid.uuid4().hex})
    check("create booking", code == 202 and b["status"] == "PENDING", f"booking={b['booking_id']} room={room_id}")
    booking_id = b["booking_id"]
    status = wait_status(booking_id, guest_a, {"AWAITING_PAYMENT", "REJECTED"})
    check("room held by inventory", status == "AWAITING_PAYMENT", status)

    code, p = call("POST", "/payments", guest_a, {"booking_id": booking_id, "amount_minor": b["amount_minor"]},
                   {"idempotency-key": uuid.uuid4().hex})
    check("payment accepted", code in (200, 402), f"http={code} status={p.get('status')}")
    expected = "CONFIRMED" if p["status"] == "SUCCEEDED" else "CANCELLED"
    status = wait_status(booking_id, guest_a, {expected})
    check("saga finished", status == expected, status)

    code, b2 = call("POST", "/bookings", guest_b, {"room_id": room_id, "check_in": CHECK_IN, "check_out": CHECK_OUT})
    status = wait_status(b2["booking_id"], guest_b, {"REJECTED", "AWAITING_PAYMENT"})
    if expected == "CONFIRMED":
        check("double booking prevented", status == "REJECTED", status)
        time.sleep(1)
        code, res2 = call("GET", f"/catalog/search?{q}", guest_b)
        left = [r for h in res2["hotels"] for o in h["offers"] for r in o["room_ids"]]
        check("search hides booked room", room_id not in left, f"room {room_id}")
    print("OK")


if __name__ == "__main__":
    main()
