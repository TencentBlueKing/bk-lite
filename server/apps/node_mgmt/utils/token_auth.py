import base64
import hashlib
import hmac
import json
from django.core.cache import cache
from django.http import JsonResponse

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.models.sidecar import SidecarApiToken
from config.components.base import SECRET_KEY
from config.components.drf import AUTH_TOKEN_HEADER_NAME
from apps.core.logger import node_logger as logger


def get_client_token(request):
    try:
        # token格式"Basic BASE64(YWRtaW46YWR:token)"
        base64_token = request.META.get(AUTH_TOKEN_HEADER_NAME).split("Basic ")[-1]
        token = base64.b64decode(base64_token).decode('utf-8')
        token = token.split(':', 1)[0]
        return token
    except Exception as e:
        logger.error(f"get_client_token error: {e}")
        return None


def check_token_auth(node_id, request):
    client_token = get_client_token(request)

    if not node_id or not client_token:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    client_token_data = decode_token(client_token)
    if node_id != client_token_data["node_id"]:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    server_token = get_node_cache_token(node_id)
    if client_token != server_token:
        return JsonResponse({'error': 'Unauthorized'}, status=401)


def is_valid_token(token):
    sidecar_api_tokens = get_cache_token()
    return token in sidecar_api_tokens


def get_cache_token():
    """ 获取缓存中的 sidecar api token """
    sidecar_api_tokens = cache.get("sidecar_api_tokens")

    if not sidecar_api_tokens:
        objs = SidecarApiToken.objects.all()
        if not objs:
            token = generate_token({"username": "admin"})
            SidecarApiToken.objects.create(token=token)
            sidecar_api_tokens = [token]
        else:
            sidecar_api_tokens = [obj.token for obj in objs]
        cache.set("sidecar_api_tokens", sidecar_api_tokens)
    return sidecar_api_tokens


def generate_token(data: dict, secret: str = SECRET_KEY):
    # 将数据序列化为 JSON 字符串
    json_data = json.dumps(data, sort_keys=True).encode('utf-8')
    # 使用 HMAC 生成 token
    signature = hmac.new(secret.encode('utf-8'), json_data, hashlib.sha256).digest()
    # 将签名与数据一起返回
    token = base64.urlsafe_b64encode(signature + b"." + json_data).decode('utf-8')
    # 将 token 存储到数据库
    obj = SidecarApiToken.objects.filter(token=token).first()
    if not obj:
        SidecarApiToken.objects.create(token=token)
    return token


def generate_node_token(node_id: str, ip: str, user: str, secret: str = SECRET_KEY):
    data = {"node_id": node_id, "ip": ip, "user": user}
    # 将数据序列化为 JSON 字符串
    json_data = json.dumps(data, sort_keys=True).encode('utf-8')
    # 使用 HMAC 生成 token
    signature = hmac.new(secret.encode('utf-8'), json_data, hashlib.sha256).digest()
    # 将签名与数据一起返回
    token = base64.urlsafe_b64encode(signature + b"." + json_data).decode('utf-8')
    SidecarApiToken.objects.update_or_create(node_id=node_id, defaults={"token": token})
    cache.set(f"node_token_{node_id}", token)
    return token


def get_node_cache_token(node_id: str):
    token = cache.get(f"node_token_{node_id}")
    if not token:
        obj = SidecarApiToken.objects.filter(node_id=node_id).first()
        if obj:
            token = obj.token
            cache.set(f"node_token_{node_id}", token)
    return token


def decode_token(token: str, secret: str = SECRET_KEY):
    # 解码 token
    decoded_data = base64.urlsafe_b64decode(token)
    signature, json_data = decoded_data.split(b".", 1)

    # 验证签名
    expected_signature = hmac.new(secret.encode('utf-8'), json_data, hashlib.sha256).digest()
    if hmac.compare_digest(signature, expected_signature):
        return json.loads(json_data)
    else:
        raise BaseAppException("无效的 token")
