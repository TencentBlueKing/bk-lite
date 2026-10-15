"""支付。sku=fail 时抛出拒卡，用来在 APM 里看到错误 span。"""

import time

from deps import cache_get, cache_set, pg_fetchall
from flask import Flask, jsonify, request

app = Flask(__name__)


class CardDeclinedError(RuntimeError):
    """支付拒卡，对应错误 Tab 的 exception.type。"""


@app.get("/health")
def health():
    return {"ok": True, "service": "payment"}


@app.post("/charges")
def charges():
    body = request.get_json(silent=True) or {}
    sku = body.get("sku", "")
    amount = body.get("amount") or 0
    cache_get(f"fraud:{sku}")
    pg_fetchall(
        "SELECT amount, status FROM (VALUES (%s::numeric, %s)) AS charges(amount, status)",
        (amount, "declined" if sku == "fail" else "paid"),
    )
    if sku == "fail":
        raise CardDeclinedError("card declined")
    cache_set(f"fraud:{sku}", "ok")
    time.sleep(0.06)
    return jsonify({"status": "paid", "sku": sku, "amount": amount})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=18084, threaded=True)
