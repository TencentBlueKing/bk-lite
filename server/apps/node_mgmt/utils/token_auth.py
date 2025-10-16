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


def generate_node_token(node_id: str, ip: str, user: str, secret: str = SECRET_KEY):
    data = {"node_id": node_id, "ip": ip, "user": user}
    # 将数据序列化为 JSON 字符串
    json_data = json.dumps(data, sort_keys=True).encode('utf-8')
    # 使用 HMAC-SHA256 生成签名（固定32字节）
    signature = hmac.new(secret.encode('utf-8'), json_data, hashlib.sha256).digest()
    # Token格式: signature(32字节) + '.'(1字节) + json_data
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
    """解码和验证 token"""
    try:
        # 解码 token
        decoded_data = base64.urlsafe_b64decode(token)
        
        # Token格式: signature(32字节) + '.'(1字节) + json_data
        # 最小长度: 32(签名) + 1(点号) + 2(最小JSON "{}")  = 35
        if len(decoded_data) < 35:
            raise BaseAppException("token 格式错误")
        
        # 前32字节是签名
        signature = decoded_data[:32]

        # 第33字节必须是点号分隔符
        if decoded_data[32:33] != b".":
            raise BaseAppException("token 格式错误")

        # 第34字节开始是JSON数据
        json_data = decoded_data[33:]

        # 验证签名
        expected_signature = hmac.new(secret.encode('utf-8'), json_data, hashlib.sha256).digest()
        if hmac.compare_digest(signature, expected_signature):
            return json.loads(json_data)
        else:
            raise BaseAppException("无效的 token")
    except (ValueError, json.JSONDecodeError, Exception) as e:
        logger.error(f"decode_token error: {e}")
        raise BaseAppException("token 解析失败")