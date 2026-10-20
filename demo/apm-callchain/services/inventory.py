"""库存。catalog 查余量，order 做预留。"""

import time

from deps import cache_get, cache_set, pg_fetchall
from flask import Flask, jsonify

app = Flask(__name__)


class InventoryCorruptError(RuntimeError):
    """库存账本损坏，对应错误 Tab 的 exception.type。"""


@app.get("/health")
def health():
    return {"ok": True, "service": "inventory"}


@app.get("/stock/<sku>")
def stock(sku: str):
    if sku == "crash":
        raise InventoryCorruptError("inventory ledger checksum mismatch")
    time.sleep(0.35 if sku == "slow" else 0.04)
    qty = 0 if sku == "stockout" else 12
    cache_get(f"stock:{sku}")
    rows = pg_fetchall(
        "SELECT sku, qty FROM (VALUES (%s, %s::int)) AS stock(sku, qty)",
        (sku, qty),
    )
    cache_set(f"stock:{sku}", str(qty))
    actual = int(rows[0][1]) if rows else qty
    return jsonify({"sku": sku, "qty": actual})


@app.post("/reserve/<sku>")
def reserve(sku: str):
    if sku == "crash":
        raise InventoryCorruptError("inventory ledger checksum mismatch")
    if sku == "stockout":
        return jsonify({"sku": sku, "error": "out of stock"}), 409
    time.sleep(1.2 if sku == "slow" else 0.12)
    pg_fetchall(
        "SELECT sku, reserved FROM (VALUES (%s, 1::int)) AS reserve(sku, reserved)",
        (sku,),
    )
    cache_set(f"reserve:{sku}", "1")
    return jsonify({"sku": sku, "reserved": 1})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=18083, threaded=True)
