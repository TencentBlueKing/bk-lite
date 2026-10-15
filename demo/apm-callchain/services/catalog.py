"""商品。查 PG 目录、Redis 缓存，再问库存。"""

import os

import requests
from deps import cache_get, cache_set, pg_fetchall
from flask import Flask, jsonify

app = Flask(__name__)
INVENTORY = os.environ.get("INVENTORY_URL", "http://127.0.0.1:18083")
PRICES = {"book": 39.0, "slow": 49.0, "fail": 39.0, "stockout": 29.0, "crash": 19.0}


@app.get("/health")
def health():
    return {"ok": True, "service": "catalog"}


@app.get("/products/<sku>")
def product(sku: str):
    if sku not in PRICES:
        return jsonify({"sku": sku, "error": "not found"}), 404
    cached = cache_get(f"product:{sku}")
    rows = pg_fetchall(
        "SELECT sku, name, price FROM (VALUES (%s, %s, %s::numeric)) AS catalog(sku, name, price)",
        (sku, sku, PRICES[sku]),
    )
    pg_fetchall(
        "SELECT id, name FROM apm_apmapplication WHERE application_id = %s LIMIT 1",
        (os.environ.get("OTEL_SERVICE_NAMESPACE") or "bklite",),
    )
    if cached is None:
        cache_set(f"product:{sku}", str(PRICES[sku]))
    stock = requests.get(f"{INVENTORY}/stock/{sku}", timeout=3)
    stock.raise_for_status()
    price = float(rows[0][2]) if rows else PRICES[sku]
    return jsonify({"sku": sku, "name": sku, "price": price, "stock": stock.json()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=18082, threaded=True)
