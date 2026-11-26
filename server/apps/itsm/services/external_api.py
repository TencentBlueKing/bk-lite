"""外部 API 复用平台安全出站请求，限制参数、超时与响应大小。"""

import json
import re
from urllib.parse import urlsplit

from rest_framework import serializers

from apps.core.mixinx import EncryptMixin
from apps.core.utils.safe_requests import safe_request
from apps.core.utils.ssrf_validator import SSRFValidator

TYPES = {
    "string": serializers.CharField,
    "integer": serializers.IntegerField,
    "number": serializers.FloatField,
    "boolean": serializers.BooleanField,
    "array": serializers.ListField,
    "object": serializers.DictField,
}


def input_serializer(schema):
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    fields = {}
    for key, spec in properties.items():
        options = {"required": key in required}
        if spec["type"] == "string":
            options["allow_blank"] = key not in required
        fields[key] = TYPES[spec["type"]](**options)
    return type("ExternalApiInput", (serializers.Serializer,), fields)


def validate_external(config):
    url = str(config.get("url") or "").strip()
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise ValueError("地址不能包含账号、密码、查询参数或片段；查询参数请通过输入参数配置")
    try:
        SSRFValidator.validate(url)
    except Exception as exc:
        raise ValueError("外部 API 地址未通过平台网络访问校验") from exc
    method = str(config.get("method") or "GET").upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ValueError("不支持的 HTTP 方法")
    schema = config.get("request_schema", {"type": "object", "properties": {}})
    if not isinstance(schema, dict) or not isinstance(schema.get("properties", {}), dict):
        raise ValueError("参数定义须为 JSON Schema 对象")
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if len(properties) > 50 or not isinstance(required, list) or any(not isinstance(k, str) or k not in properties for k in required):
        raise ValueError("参数最多 50 个，必填项必须存在")
    clean = {}
    for key, spec in properties.items():
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key)
            or key in dir(serializers.Serializer)
            or not isinstance(spec, dict)
            or spec.get("type") not in TYPES
        ):
            raise ValueError("参数名称或类型无效")
        clean[key] = {"type": spec["type"], "description": str(spec.get("description", ""))[:500]}
    token = str(config.get("token") or "")
    if len(token) > 4096 or "\n" in token or "\r" in token:
        raise ValueError("认证令牌无效")
    return {
        "transport": "external",
        "url": url,
        "method": method,
        "token": token,
        "request_schema": {"type": "object", "properties": clean, "required": required},
    }


def execute_external(config, inputs):
    schema = config.get("request_schema") or {"properties": {}}
    if set(inputs) - schema.get("properties", {}).keys():
        raise ValueError("接口参数不在 API 声明中")
    serializer = input_serializer(schema)(data=inputs)
    if not serializer.is_valid():
        raise ValueError("外部 API 输入参数不符合定义")
    headers = {"Accept": "application/json"}
    if config.get("token"):
        token = EncryptMixin.get_cipher_suite().decrypt(config["token"].encode()).decode()
        headers["Authorization"] = f"Bearer {token}"
    method = config["method"]
    response = safe_request(
        method,
        config["url"],
        headers=headers,
        timeout=(3, 10),
        allow_redirects=False,
        stream=True,
        **{("params" if method == "GET" else "json"): serializer.validated_data},
    )
    try:
        if not 200 <= response.status_code < 300:
            raise ValueError(f"外部 API 返回 HTTP {response.status_code}")
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 1024 * 1024:
                raise ValueError("外部 API 返回超过 1MB")
            chunks.append(chunk)
        try:
            return json.loads(b"".join(chunks))
        except (ValueError, UnicodeError) as exc:
            raise ValueError("外部 API 必须返回 JSON") from exc
    finally:
        response.close()
