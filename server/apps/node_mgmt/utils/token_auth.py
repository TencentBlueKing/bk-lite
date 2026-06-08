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


def get_client_token(request):
    auth_header = request.META.get(AUTH_TOKEN_HEADER_NAME)
    if not auth_header:
        logger.warning("【Sidecar认证失败】请求未携带 Authorization 认证头。"
                       "可能原因：1) Sidecar 配置缺少 api_token；2) 中间的反向代理/网关把 Authorization 头丢弃了。"
                       "处理建议：检查 Sidecar 配置文件中的 token 是否填写，以及 Nginx/网关是否透传 Authorization 头。")
        return None
    try:
        # token格式"Basic BASE64(YWRtaW46YWR:token)"
        base64_token = auth_header.split("Basic ")[-1]
        token = base64.b64decode(base64_token).decode('utf-8')
        token = token.split(':', 1)[0]
        return token
    except Exception as e:
        logger.warning(f"【Sidecar认证失败】Authorization 认证头格式错误，无法解析。原始头内容前缀：{auth_header[:20]!r}。"
                       f"正确格式应为 'Basic <base64编码的token>'。错误详情：{e}。"
                       f"处理建议：检查 Sidecar 是否被正确安装、token 是否被截断或篡改。")
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
        logger.warning("【Sidecar认证失败】请求中缺少节点ID(node_id)。"
                       "处理建议：检查 Sidecar 上报请求的参数是否完整。")
        raise UnauthorizedException("缺少必要的认证信息：节点ID为空")

    if not client_token:
        # 具体原因已在 get_client_token 中打印
        raise UnauthorizedException("缺少必要的认证信息：未获取到有效的认证Token")

    client_token_data = decode_token(client_token, node_id=node_id)
    if node_id != client_token_data["node_id"]:
        logger.warning(f"【Sidecar认证失败】节点ID与Token不匹配。"
                       f"请求的节点ID={node_id}，但Token中记录的节点ID={client_token_data.get('node_id')}。"
                       f"可能原因：该 Sidecar 使用了属于其它节点的 token（如配置被复制到了另一台机器）。"
                       f"处理建议：在该机器上重新执行安装命令，重新签发专属 token。")
        raise UnauthorizedException("节点ID与Token不匹配")

    server_token = get_node_cache_token(node_id)
    if not server_token:
        logger.warning(f"【Sidecar认证失败】服务端未找到节点 {node_id} 的 token 记录（缓存和数据库中均不存在）。"
                       f"可能原因：1) 该节点从未在本平台注册/安装；2) 节点已被删除；3) 数据库中的 SidecarApiToken 记录丢失。"
                       f"处理建议：在节点管理中确认该节点是否存在，必要时在该机器上重新执行安装命令重新签发 token。")
        raise UnauthorizedException("Token无效或已过期：服务端无此节点的Token记录")

    if client_token != server_token:
        logger.warning(f"【Sidecar认证失败】节点 {node_id} 的 token 与服务端记录不一致。"
                       f"可能原因：1) 该节点的 token 已被重新签发，但 Sidecar 仍在使用旧 token；"
                       f"2) Sidecar 配置中的 token 被手动改动。"
                       f"处理建议：在该机器上重新执行安装命令，用最新的 token 覆盖旧配置。")
        raise UnauthorizedException("Token无效或已过期：与服务端记录不一致")

    logger.info(f"【Sidecar认证成功】节点 {node_id} 认证通过。")


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
    node_desc = f"节点 {node_id} 的" if node_id else ""
    try:
        # 解码 token
        decoded_data = base64.urlsafe_b64decode(token)

        # Token格式: signature(32字节) + '.'(1字节) + json_data
        # 最小长度: 32(签名) + 1(点号) + 2(最小JSON "{}")  = 35
        if len(decoded_data) < 35:
            logger.warning(f"【Sidecar认证失败】{node_desc}Token 内容长度不足，格式非法。"
                           f"处理建议：Token 可能被截断，请在该机器上重新执行安装命令重新签发。")
            raise BaseAppException("token 格式错误")

        # 前32字节是签名
        signature = decoded_data[:32]

        # 第33字节必须是点号分隔符
        if decoded_data[32:33] != b".":
            logger.warning(f"【Sidecar认证失败】{node_desc}Token 结构非法（缺少分隔符）。"
                           f"处理建议：Token 可能被篡改，请在该机器上重新执行安装命令重新签发。")
            raise BaseAppException("token 格式错误")

        # 第34字节开始是JSON数据
        json_data = decoded_data[33:]

        # 验证签名
        expected_signature = hmac.new(secret.encode('utf-8'), json_data, hashlib.sha256).digest()
        if hmac.compare_digest(signature, expected_signature):
            return json.loads(json_data)
        else:
            logger.warning(f"【Sidecar认证失败】{node_desc}Token 签名校验不通过。"
                           f"最常见原因：服务端的 SECRET_KEY 与签发该 Token 时不一致"
                           f"（例如服务重新部署后 SECRET_KEY 变了，或多个后端副本的 SECRET_KEY 不统一）。"
                           f"处理建议：1) 确认所有后端实例的 SECRET_KEY 配置一致且未变更；"
                           f"2) 若 SECRET_KEY 确实已变更，需在所有节点上重新执行安装命令重新签发 token。")
            raise BaseAppException("无效的 token")
    except BaseAppException:
        raise
    except Exception as e:
        logger.warning(f"【Sidecar认证失败】{node_desc}Token 解析异常：{e}。"
                       f"处理建议：Token 可能损坏或格式不正确，请在该机器上重新执行安装命令重新签发。")
        raise BaseAppException("token 解析失败")