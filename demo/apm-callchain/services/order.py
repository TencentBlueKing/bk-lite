"""订单。预留库存，再请求支付。"""

import os

import requests
from deps import cache_set, pg_fetchall, resolve_demo_sku
from flask import Flask, jsonify, request

app = Flask(__name__)
INVENTORY = os.environ.get("INVENTORY_URL", "http://127.0.0.1:18083")
PAYMENT = os.environ.get("PAYMENT_URL", "http://127.0.0.1:18084")


@app.get("/health")
def health():
    return {"ok": True, "service": "order"}


@app.post("/orders")
def create_order():
    body = request.get_json(silent=True) or {}
    requested = body.get("sku", "book")
    sku = resolve_demo_sku(requested)
    if sku is None:
        return jsonify({"sku": requested, "status": "invalid_sku"}), 400
    pg_fetchall(
        "SELECT sku, ordered_at FROM (VALUES (%s, now())) AS orders(sku, ordered_at)",
        (sku,),
    )
    cache_set(f"order:{sku}", sku)
    reserved = requests.post(f"{INVENTORY}/reserve/{sku}", timeout=3)
    if reserved.status_code == 409:
        return jsonify({"sku": sku, "status": "out_of_stock"}), 409
    reserved.raise_for_status()
    charged = requests.post(
        f"{PAYMENT}/charges",
        json={"sku": sku, "amount": body.get("price")},
        timeout=3,
    )
    if charged.status_code >= 400:
        return jsonify({"sku": sku, "status": "payment_failed"}), 502
    return jsonify({"sku": sku, "status": "created", "reserve": reserved.json(), "payment": charged.json()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=18081, threaded=True)
