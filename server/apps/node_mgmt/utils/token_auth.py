import base64
import hashlib
import hmac
import json
from django.core.cache import cache

from apps.core.exceptions.base_app_exception import BaseAppException, UnauthorizedException
from apps.node_mgmt.models.sidecar import SidecarApiToken
from config.components.base import SECRET_KEY
from config.components.drf import AUTH_TOKEN_HEADER_NAME
from apps.core.logger import node_logger as logger


def _log_auth_failure(reason, *, node_id="-", error_type="-"):
    logger.warning(
        "event=sidecar_auth_failed reason=%s node_id=%s error_type=%s",
        reason,
        node_id or "-",
        error_type or "-",
    )


def get_client_token(request):
    auth_header = request.META.get(AUTH_TOKEN_HEADER_NAME)
    if not auth_header:
        _log_auth_failure("missing_header")
        return None
    try:
        # token格式"Basic BASE64(YWRtaW46YWR:token)"
        base64_token = auth_header.split("Basic ")[-1]
        token = base64.b64decode(base64_token).decode('utf-8')
        token = token.split(':', 1)[0]
        return token
    except Exception as e:
        _log_auth_failure("malformed_header", error_type=type(e).__name__)
        return None


def check_token_auth(node_id, request):
    """
    校验节点Token认证

    Args:
        node_id: 节点ID
        request: HTTP请求对象

    Raises:
        UnauthorizedException: 当认证失败时抛出异常
    """
    client_token = get_client_token(request)

    if not node_id:
        _log_auth_failure("missing_node_id")
        raise UnauthorizedException("缺少必要的认证信息：节点ID为空")

    if not client_token:
        # 具体原因已在 get_client_token 中打印
        raise UnauthorizedException("缺少必要的认证信息：未获取到有效的认证Token")

    client_token_data = decode_token(client_token, node_id=node_id)
    if node_id != client_token_data["node_id"]:
        _log_auth_failure("node_mismatch", node_id=node_id)
        raise UnauthorizedException("节点ID与Token不匹配")

    server_token = get_node_cache_token(node_id)
    if not server_token:
        _log_auth_failure("no_server_token", node_id=node_id)
        raise UnauthorizedException("Token无效或已过期：服务端无此节点的Token记录")

    if client_token != server_token:
        _log_auth_failure("token_mismatch", node_id=node_id)
        raise UnauthorizedException("Token无效或已过期：与服务端记录不一致")


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


def decode_token(token: str, secret: str = SECRET_KEY, node_id: str = ""):
    """解码和验证 token"""
    try:
        # 解码 token
        decoded_data = base64.urlsafe_b64decode(token)

        # Token格式: signature(32字节) + '.'(1字节) + json_data
        # 最小长度: 32(签名) + 1(点号) + 2(最小JSON "{}")  = 35
        if len(decoded_data) < 35:
            _log_auth_failure("bad_length", node_id=node_id)
            raise BaseAppException("token 格式错误")

        # 前32字节是签名
        signature = decoded_data[:32]

        # 第33字节必须是点号分隔符
        if decoded_data[32:33] != b".":
            _log_auth_failure("bad_structure", node_id=node_id)
            raise BaseAppException("token 格式错误")

        # 第34字节开始是JSON数据
        json_data = decoded_data[33:]

        # 验证签名
        expected_signature = hmac.new(secret.encode('utf-8'), json_data, hashlib.sha256).digest()
        if hmac.compare_digest(signature, expected_signature):
            return json.loads(json_data)
        else:
            _log_auth_failure("bad_signature", node_id=node_id)
            raise BaseAppException("无效的 token")
    except BaseAppException:
        raise
    except Exception as e:
        _log_auth_failure("parse_error", node_id=node_id, error_type=type(e).__name__)
        raise BaseAppException("token 解析失败")
