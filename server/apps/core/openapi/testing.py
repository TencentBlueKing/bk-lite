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


def create_system_tenant(
    team_id: int,
    username: str = None,
    *,
    system_id: str = "itsm",
    scope: dict | None = None,
    plaintext_token: str | None = None,
):
    """创建一个可经系统 Token 调用网关的租户身份。

    登记 system_id、签发（或复用）系统 Token，并创建目标用户及其直属组织。
    返回 (base_user, plaintext_token)。同一系统 Token 可对多个组织各调一次本函数
    （传入 plaintext_token）以构造双租户 acting 主体。
    """
    from apps.system_mgmt.models import Group, SystemAPIToken
    from apps.system_mgmt.models import User as SystemUser

    Group.objects.get_or_create(id=team_id, defaults={"name": f"team-{team_id}"})
    user = UserFactory(
        group_list=[team_id], **({"username": username} if username else {})
    )
    SystemUser.objects.update_or_create(
        username=user.username,
        domain=user.domain,
        defaults={
            "display_name": user.username,
            "email": f"{user.username}@example.com",
            "password": "x",
            "group_list": [team_id],
        },
    )
    if plaintext_token is None:
        plaintext_token = SystemAPIToken.generate_secret()
    if SystemAPIToken.find_live_by_secret(plaintext_token) is None:
        SystemAPIToken.objects.create(
            system_id=system_id,
            name=system_id,
            secret_hash=SystemAPIToken.hash_secret(plaintext_token),
            scope=scope if scope is not None else {"mode": "all"},
            enabled=True,
            created_by="admin",
            created_by_domain="domain.com",
        )
    return user, plaintext_token


def bearer(token: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def acting_headers(token: str, user, team_id: int) -> dict:
    return {
        **bearer(token),
        "HTTP_X_BKLITE_ACTING_USER": f"{user.username}@{user.domain}",
        "HTTP_X_BKLITE_ACTING_TEAM": str(team_id),
    }
