"""
team_utils — 当前组织上下文读取工具

统一的 current_team 读取入口，屏蔽「browser cookie」与「API Key 注入属性」两种来源的差异。

使用方式：
    from apps.core.utils.team_utils import get_current_team

    # 返回字符串或 default；调用方自行 int() 转换
    team_str = get_current_team(request)          # -> "7" | None
    team_id  = get_current_team(request, "0")     # -> "7" | "0"

来源优先级：
  1. request._api_current_team  —— APISecretMiddleware 在无浏览器 cookie 时注入的组织 ID
  2. request.COOKIES["current_team"] —— 浏览器正常登录时携带的 cookie
  3. default（默认 None）

这样可以保证 API Key 调用和浏览器调用在下游代码中使用同一读取路径，
同时不再污染 request.COOKIES 只读 dict（违反 Django 约定）。
"""


def get_current_team(request, default=None):
    """
    获取当前请求的组织上下文字符串。

    :param request: Django HttpRequest 对象
    :param default: 找不到时的返回值（str | None）
    :return: 组织 ID 字符串，或 default
    """
    # 优先使用 API Key 中间件注入的属性（仅在无浏览器 cookie 时设置）
    api_team = getattr(request, "_api_current_team", None)
    if api_team is not None:
        return str(api_team)

    # 其次使用浏览器 cookie
    cookie_team = request.COOKIES.get("current_team")
    if cookie_team is not None:
        return str(cookie_team)

    return default
