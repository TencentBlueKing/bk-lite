"""本包厂商请求层：微信 OAuth HTTP。能力模块不要再抄一份 requests。"""

import requests

WECHAT_TIMEOUT = 10
WECHAT_AUTHORIZE_URL = "https://open.weixin.qq.com/connect/qrconnect"
WECHAT_ACCESS_TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
WECHAT_USER_INFO_URL = "https://api.weixin.qq.com/sns/userinfo"


def _get_config_value(config: dict, key: str, default: str):
    return (config or {}).get(key) or default


def _get(url, params, *, encoding=None):
    """本包 HTTP GET；能力模块不要各自再抄 requests。"""
    response = requests.get(url, params=params, timeout=WECHAT_TIMEOUT)
    if encoding is not None:
        response.encoding = encoding
    return response
