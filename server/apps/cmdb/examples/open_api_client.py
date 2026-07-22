"""CMDB OpenAPI 的最小 Python 调用示例。"""

import argparse
import json
import os
from urllib.parse import quote

import requests


class CMDBOpenAPIClientError(RuntimeError):
    """OpenAPI 返回失败结果或非法响应。"""


class CMDBOpenAPIClient:
    def __init__(self, base_url, api_secret, *, timeout=10, session=None):
        self.api_base = f"{base_url.rstrip('/')}/api/v1/cmdb/api/open"
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Api-Authorization": api_secret,
                "Accept": "application/json",
            }
        )

    def _request(self, method, path, **kwargs):
        response = self.session.request(
            method,
            f"{self.api_base}{path}",
            timeout=self.timeout,
            **kwargs,
        )
        try:
            payload = response.json()
        except requests.exceptions.JSONDecodeError as exc:
            raise CMDBOpenAPIClientError(
                f"服务返回非 JSON 响应，HTTP {response.status_code}"
            ) from exc
        if not isinstance(payload, dict) or not payload.get("result"):
            code = payload.get("code", "unknown") if isinstance(payload, dict) else "unknown"
            message = payload.get("message", "响应格式非法") if isinstance(payload, dict) else "响应格式非法"
            raise CMDBOpenAPIClientError(
                f"CMDB OpenAPI 调用失败：HTTP {response.status_code}，{code}，{message}"
            )
        response.raise_for_status()
        return payload["data"]

    def list_instances(self, model_id, *, page=1, page_size=20, order="", filters=None):
        return self._request(
            "GET",
            f"/models/{quote(model_id, safe='')}/instances",
            params={
                "page": page,
                "page_size": page_size,
                "order": order,
                "filters": json.dumps(filters or [], ensure_ascii=False),
            },
        )

    def create_instance(self, model_id, attributes):
        return self._request(
            "POST",
            f"/models/{quote(model_id, safe='')}/instances",
            json=attributes,
        )


def main():
    parser = argparse.ArgumentParser(description="调用 CMDB OpenAPI 查询或创建实例")
    parser.add_argument("--base-url", required=True, help="BK-Lite 地址，如 http://127.0.0.1:8011")
    parser.add_argument("--model-id", required=True, help="模型 ID，如 host")
    parser.add_argument("--action", choices=("list", "create"), default="list")
    parser.add_argument("--payload", default="{}", help="create 时使用的实例属性 JSON")
    parser.add_argument("--filters", default="[]", help="list 时使用的过滤条件 JSON 数组")
    args = parser.parse_args()

    api_secret = os.environ.get("CMDB_API_SECRET")
    if not api_secret:
        parser.error("请先设置环境变量 CMDB_API_SECRET")

    client = CMDBOpenAPIClient(args.base_url, api_secret)
    if args.action == "create":
        result = client.create_instance(args.model_id, json.loads(args.payload))
    else:
        result = client.list_instances(args.model_id, filters=json.loads(args.filters))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
