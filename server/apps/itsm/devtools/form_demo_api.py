"""本地表单联调服务：仅监听回环，数据全为虚构，不接触业务数据库。"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

DEPARTMENTS = [{"id": "rd", "name": "研发部"}, {"id": "ops", "name": "运维部"}, {"id": "finance", "name": "财务部"}]
ASSETS = [
    {
        "id": f"host-{i:03}",
        "name": f"演示服务器 {i:02}",
        "department": DEPARTMENTS[(i - 1) % 3]["id"],
        "environment": ["dev", "test", "prod"][(i - 1) % 3],
        "amount": 5000 + i * 500,
    }
    for i in range(1, 13)
]
REGIONS = [
    {"id": "east", "name": "华东", "children": [{"id": "sh", "name": "上海"}, {"id": "hz", "name": "杭州"}]},
    {"id": "south", "name": "华南", "children": [{"id": "sz", "name": "深圳"}, {"id": "gz", "name": "广州"}]},
]
PLANS = [{"id": f"plan-{i}", "name": name, "amount": i * 100} for i, name in enumerate(["云主机", "MySQL", "Redis", "对象存储"], 1)]


def query(path, params):
    datasets = {"/departments": DEPARTMENTS, "/assets": ASSETS, "/regions": REGIONS, "/plans": PLANS}
    if path == "/health":
        return {"status": "ok", "service": "itsm-form-demo"}
    if path not in datasets:
        raise KeyError(path)
    rows = datasets[path]
    keyword = str(params.get("keyword", "")).strip().lower()
    rows = [r for r in rows if not keyword or keyword in r["name"].lower() or keyword in r["id"].lower()]
    for key in ["department", "environment"]:
        if params.get(key):
            rows = [r for r in rows if r.get(key) == params[key]]
    page = max(1, int(params.get("page", 1)))
    size = max(1, min(100, int(params.get("page_size", 20))))
    return {"data": {"items": rows[(page - 1) * size : page * size], "total": len(rows)}}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        try:
            data, status = query(parsed.path, {k: v[-1] for k, v in parse_qs(parsed.query).items()}), 200
        except KeyError:
            data, status = {"message": "接口不存在"}, 404
        except ValueError:
            data, status = {"message": "页码和每页条数必须为整数"}, 400
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8096), Handler).serve_forever()
