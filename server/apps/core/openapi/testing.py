"""双租户测试基建（安全红线 4：双租户测试是暴露的准入条件）。

用法：为被测暴露函数构造两个组织的调用身份，断言读隔离与写归属。
"""

from apps.base.tests.factories import UserAPISecretFactory, UserFactory


def create_api_tenant(team_id: int, username: str = None):
    """创建一个可经 API 令牌调用网关的租户身份。

    返回 (base_user, plaintext_token)。涵盖认证链路全部依赖：
    base.User、system_mgmt.User（backends 的 SystemUser 校验）、UserAPISecret。
    """
    from apps.system_mgmt.models import Group
    from apps.system_mgmt.models import User as SystemUser

    user = UserFactory(group_list=[team_id], **({"username": username} if username else {}))
    SystemUser.objects.get_or_create(username=user.username, domain=user.domain)
    Group.objects.get_or_create(id=team_id, defaults={"name": f"team-{team_id}"})
    secret = UserAPISecretFactory(
        username=user.username, domain=user.domain, team=team_id
    )
    return user, secret.api_secret


def bearer(token: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}
