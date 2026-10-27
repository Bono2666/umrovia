#!/usr/bin/env python3
"""Uji beban & konkurensi API Umrovia (S19). Hanya stdlib: tidak perlu k6/locust.

1. Baca: N pengguna paralel memanggil endpoint utama selama D detik → p50/p95/p99, galat.
2. Konkurensi kursi terakhir (UAT-02/OPS01): K booking berebut 1 kursi → tepat 1 berhasil.

  python3 load_test.py --base http://localhost:8030 --email owner@load.test --password '...' \
      --users 10 --duration 30 --report hasil.json
Target Spec §13: p95 baca < 500 ms (baseline pilot).
"""
import argparse
import http.cookiejar
import json
import statistics
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone


class Session:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ""

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Content-Type": "application/json", "X-CSRFToken": self.csrf, "Referer": self.base + "/", "Origin": self.base,
            "Idempotency-Key": f"load-{time.time_ns()}-{threading.get_ident()}",
        })
        start = time.perf_counter()
        try:
            with self.opener.open(request, timeout=30) as response:  # noqa: S310 - URL dari argumen operator
                payload = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            payload, status = error.read(), error.code
        elapsed = (time.perf_counter() - start) * 1000
        return status, (json.loads(payload) if payload[:1] in (b"{", b"[") else payload), elapsed

    def share(self, other):
        """Pakai sesi login yang sama (batas login 10/menit tidak ikut teruji di sini)."""
        for cookie in other.jar:
            self.jar.set_cookie(cookie)
        self.csrf = other.csrf
        return self

    def login(self, email, password):
        _, body, _ = self.call("GET", "/api/v1/auth/csrf")
        self.csrf = body["csrfToken"]
        status, body, _ = self.call("POST", "/api/v1/auth/login", {"email": email, "password": password})
        if status != 200:
            raise SystemExit(f"login gagal {status}: {body}")
        self.csrf = next((c.value for c in self.jar if c.name == "csrftoken"), self.csrf)


def percentile(values, q):
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(round(q / 100 * (len(ordered) - 1))))], 1) if ordered else None


def read_load(args, departure_ids, shared):
    endpoints = [
        # Daftar besar dipanggil seperti UI (paginasi 50 baris, S19).
        "/api/v1/me", "/api/v1/bookings?page=1", "/api/v1/pilgrims", "/api/v1/departures", "/api/v1/invoices?page=1", "/api/v1/payments?page=1",
        "/api/v1/wallet", "/api/v1/notifications", "/api/v1/reports/operational", "/api/v1/reports/finance",
    ] + [f"/api/v1/departures/{departure_ids[0]}/manifest"]
    samples = {path: [] for path in endpoints}
    errors = {path: 0 for path in endpoints}
    stop = time.time() + args.duration
    lock = threading.Lock()

    def user(index):
        session = Session(args.base).share(shared)
        i = index
        while time.time() < stop:
            path = endpoints[i % len(endpoints)]
            status, _, ms = session.call("GET", path)
            with lock:
                samples[path].append(ms)
                if status >= 400:
                    errors[path] += 1
            i += 1

    with ThreadPoolExecutor(args.users) as pool:
        list(pool.map(user, range(args.users)))
    rows = []
    for path in endpoints:
        values = samples[path]
        rows.append({"endpoint": path.replace(departure_ids[0], "{id}"), "requests": len(values), "errors": errors[path],
                     "p50_ms": percentile(values, 50), "p95_ms": percentile(values, 95), "p99_ms": percentile(values, 99)})
    everything = [v for values in samples.values() for v in values]
    total = {"requests": len(everything), "errors": sum(errors.values()), "rps": round(len(everything) / args.duration, 1),
             "p50_ms": percentile(everything, 50), "p95_ms": percentile(everything, 95), "p99_ms": percentile(everything, 99),
             "mean_ms": round(statistics.mean(everything), 1) if everything else None}
    return rows, total


def seat_race(args, owner):
    _, packages, _ = owner.call("GET", "/api/v1/packages")
    start = (datetime.now(timezone.utc) + timedelta(days=200)).isoformat()
    status, dep, _ = owner.call("POST", "/api/v1/departures", {"package": packages["results"][0]["id"], "start_at": start, "city_of_origin": "Jakarta", "seat_capacity": 1})
    assert status == 201, dep
    owner.call("POST", f"/api/v1/departures/{dep['id']}/transition", {"target": "OPEN"})
    room = next((r["room_type"] for r in packages["results"][0].get("room_prices") or []), None)
    bookings = []
    for i in range(args.racers):
        _, pilgrim, _ = owner.call("POST", "/api/v1/pilgrims", {"name": f"Jamaah Rebutan {i}"})
        body = {"departure": dep["id"], "participants": [pilgrim["id"]]}
        if room:
            body["room_types"] = {pilgrim["id"]: room}
        status, booking, _ = owner.call("POST", "/api/v1/bookings", body)
        assert status == 201, booking
        bookings.append(booking["id"])
    barrier = threading.Barrier(args.racers)

    def reserve(booking_id):
        session = Session(args.base).share(owner)
        barrier.wait()
        status, _, ms = session.call("POST", f"/api/v1/bookings/{booking_id}/transition", {"target": "RESERVED"})
        return status, ms

    with ThreadPoolExecutor(args.racers) as pool:
        results = list(pool.map(reserve, bookings))
    _, final, _ = owner.call("GET", f"/api/v1/departures/{dep['id']}")
    return {"racers": args.racers, "succeeded": sum(1 for s, _ in results if s == 200), "rejected_400": sum(1 for s, _ in results if s == 400),
            "other": sorted({s for s, _ in results if s not in (200, 400)}), "seats_taken": final["seats_taken"], "capacity": final["seat_capacity"],
            "max_ms": round(max(ms for _, ms in results), 1)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--racers", type=int, default=20)
    parser.add_argument("--report")
    args = parser.parse_args()
    probe = Session(args.base)
    probe.login(args.email, args.password)
    _, departures, _ = probe.call("GET", "/api/v1/departures")
    rows, total = read_load(args, [d["id"] for d in departures["results"]], probe)
    race = seat_race(args, probe)
    report = {"base": args.base, "users": args.users, "duration_s": args.duration, "at": datetime.now(timezone.utc).isoformat(), "total": total, "endpoints": rows, "seat_race": race,
              "pass": total["errors"] == 0 and (total["p95_ms"] or 0) < 500 and race["succeeded"] == 1 and race["seats_taken"] == 1}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.report:
        with open(args.report, "w") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
