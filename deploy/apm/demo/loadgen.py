from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request


TARGET = os.environ.get("APM_DEMO_TARGET", "http://apm-demo-storefront:8080")
INTERVAL = float(os.environ.get("APM_DEMO_INTERVAL_SECONDS", "0.35"))
SCENARIOS = (
    (48, "GET", "/api/products"),
    (22, "POST", "/api/checkout"),
    (10, "GET", "/api/profile"),
    (8, "POST", "/api/checkout?scenario=slow"),
    (8, "POST", "/api/checkout?scenario=payment-failure"),
    (4, "GET", "/api/products?scenario=inventory-failure"),
)


def choose_scenario() -> tuple[str, str]:
    roll = random.randint(1, 100)
    cumulative = 0
    for weight, method, path in SCENARIOS:
        cumulative += weight
        if roll <= cumulative:
            return method, path
    return "GET", "/api/products"


def send(method: str, path: str) -> int:
    body = json.dumps({"source": "apm-demo-loadgen"}).encode() if method == "POST" else None
    request = urllib.request.Request(
        f"{TARGET}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json", "User-Agent": "bk-lite-apm-demo/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as result:
            result.read()
            return result.status
    except urllib.error.HTTPError as error:
        error.read()
        return error.code


if __name__ == "__main__":
    print(f"APM demo load generator targeting {TARGET}", flush=True)
    while True:
        method, path = choose_scenario()
        try:
            status = send(method, path)
            print(f"{method} {path} -> {status}", flush=True)
        except Exception as error:
            print(f"{method} {path} -> unavailable ({type(error).__name__})", flush=True)
        time.sleep(INTERVAL)
