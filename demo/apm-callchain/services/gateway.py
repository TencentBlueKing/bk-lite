"""入口。先问商品，再下单。"""

import os

import requests
from deps import cache_get, cache_set, resolve_demo_sku
from flask import Flask, jsonify, request

app = Flask(__name__)
CATALOG = os.environ.get("CATALOG_URL", "http://127.0.0.1:18082")
ORDER = os.environ.get("ORDER_URL", "http://127.0.0.1:18081")


@app.get("/health")
def health():
    return {"ok": True, "service": "gateway"}


@app.get("/checkout")
def checkout():
    requested = request.args.get("sku", "book")
    sku = resolve_demo_sku(requested)
    if sku is None:
        return jsonify({"sku": requested, "status": "catalog_failed"}), 404
    cache_get(f"session:{sku}")
    cache_set(f"session:{sku}", sku)
    try:
        product = requests.get(f"{CATALOG}/products/{sku}", timeout=3)
        product.raise_for_status()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        return jsonify({"sku": sku, "status": "catalog_failed"}), status
    body = product.json()
    order = requests.post(f"{ORDER}/orders", json={"sku": sku, "price": body.get("price")}, timeout=3)
    return jsonify({"product": body, "order": order.json()}), order.status_code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=18080, threaded=True)
