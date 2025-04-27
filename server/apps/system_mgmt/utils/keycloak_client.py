import logging

from django.conf import settings
from keycloak import KeycloakAdmin, KeycloakOpenID
from singleton_decorator import singleton

from apps.core.entities.user_token_entity import UserTokenEntity
from apps.system_mgmt.constants import BUILT_IN_ROLES
from apps.system_mgmt.utils.db_utils import SQLExecute


@singleton
class KeyCloakClient:
    def __init__(self):
        self.admin_client = KeycloakAdmin(
            server_url=settings.KEYCLOAK_URL_API,
            username=settings.KEYCLOAK_ADMIN_USERNAME,
            password=settings.KEYCLOAK_ADMIN_PASSWORD,
        )
        self.realm_client = KeycloakAdmin(
            server_url=settings.KEYCLOAK_URL_API,
            username=settings.KEYCLOAK_ADMIN_USERNAME,
            password=settings.KEYCLOAK_ADMIN_PASSWORD,
            realm_name=settings.KEYCLOAK_REALM,
            client_id="admin-cli",
            user_realm_name="master",
        )
        self.client_secret_key, self.client_id = None, None
        self.openid_client = None
        self.logger = logging.getLogger("app")

    def get_openid_client(self):
        if self.openid_client is None:
            self.openid_client = KeycloakOpenID(
                server_url=settings.KEYCLOAK_URL_API,
                client_id=settings.KEYCLOAK_CLIENT_ID,
                realm_name=settings.KEYCLOAK_REALM,
                client_secret_key=self.get_client_secret_key(),
            )
        return self.openid_client

    def set_client_secret_and_id(self):
        """设置域id与secret"""
        client_secret_key, client_id = None, None
        clients = self.realm_client.get_clients()
        for client in clients:
            if client["clientId"] == settings.KEYCLOAK_CLIENT_ID:
                client_id = client["id"]
                client_secret_key = client["secret"]
                break
        self.client_secret_key, self.client_id = client_secret_key, client_id

    def get_client_secret_key(self):
        """获取客户端secret_key"""
        if self.client_secret_key is None:
            self.set_client_secret_and_id()
        return self.client_secret_key

    def get_client_id(self):
        """获取客户端client_id"""
        if self.client_id is None:
            self.set_client_secret_and_id()
        return self.client_id

    def get_realm_client(self):
        return self.realm_client

    def token_is_valid(self, token) -> (bool, dict):
        try:
            openid_client = self.get_openid_client()
            token_info = openid_client.introspect(token)
            if token_info.get("active"):
                return True, token_info
            else:
                return False, {}
        except Exception:
            return False, {}

    def get_userinfo(self, token: str):
        openid_client = self.get_openid_client()
        return openid_client.userinfo(token)

    def get_roles(self, token: str) -> list:
        try:
            openid_client = self.get_openid_client()
            token_info = openid_client.introspect(token)
            return token_info["realm_access"]["roles"]
        except Exception:
            self.logger.error("获取用户角色失败")
            return []

    def is_super_admin(self, token: str) -> bool:
        try:
            openid_client = self.get_openid_client()
            token_info = openid_client.introspect(token)
            return "admin" in token_info["realm_access"]["roles"]
        except:  # noqa
            return False

    def has_permission(self, token: str, permission: str) -> bool:
        try:
            openid_client = self.get_openid_client()
            openid_client.uma_permissions(token, permission)
            return True
        except:  # noqa
            return False

    def get_token(self, username: str, password: str) -> UserTokenEntity:
        try:
            openid_client = self.get_openid_client()
            token = openid_client.token(username, password)
            return UserTokenEntity(token=token["access_token"], error_message="", success=True)
        except Exception as e:
            self.logger.error(e)
            return UserTokenEntity(token=None, error_message="用户名密码不匹配", success=False)

    def get_user_groups(self, sub, is_admin):
        all_groups = self.realm_client.get_groups({"search": ""})
        if is_admin:
            return self.get_child_groups(all_groups)
        res = self.realm_client.get_user_groups(sub, {"search": ""})
        return self.get_normal_user_all_groups(res, all_groups)

    def get_normal_user_all_groups(self, res, all_groups):
        exist_data = [i["id"] for i in res]
        return_data = [{"id": i["id"], "name": i["name"], "path": i["path"]} for i in res]
        group_ids = [i["id"] for i in return_data]
        for i in all_groups:
            if i["id"] not in group_ids:
                continue
            sub_groups = i.pop("subGroups", [])
            group_children = [u for u in self.get_child_groups(sub_groups) if u["id"] not in exist_data]
            return_data.extend(group_children)
            exist_data.extend([u["id"] for u in group_children])
        return return_data

    def get_child_groups(self, groups):
        return_data = []
        exist_data = []
        for i in groups:
            sub_groups = i.pop("subGroups", [])
            if i["id"] not in return_data:
                return_data.append({"id": i["id"], "name": i["name"], "path": i["path"]})
                exist_data.append(i["id"])
            if sub_groups:
                group_children = [u for u in self.get_child_groups(sub_groups) if u["id"] not in exist_data]
                return_data.extend(group_children)
                exist_data.extend([u["id"] for u in group_children])
        return return_data

    def get_realm_roles(self):
        result = self.realm_client.get_realm_roles()
        roles = [i for i in result if i.get("name") not in BUILT_IN_ROLES]
        return roles

    def get_realm_roles_of_user(self, user_id):
        """获取用户关联的角色，并过滤掉内置角色"""
        self_roles = self.realm_client.get_realm_roles_of_user(user_id)
        self_role_name_set = {i["name"] for i in self_roles}
        all_roles = self.realm_client.get_composite_realm_roles_of_user(user_id)
        roles = []
        for role_info in all_roles:
            if role_info.get("name") in BUILT_IN_ROLES:
                continue
            if role_info.get("name") in self_role_name_set:
                role_info.update(role_type="user")
            else:
                role_info.update(role_type="group")
            roles.append(role_info)
        return roles

    def create_permission(self, client_id, menu_ids, permission_name, policy_id):
        permission = {
            "resources": menu_ids,
            "policies": [policy_id],
            "name": f"{permission_name}-permission",
            "description": "",
            "decisionStrategy": "AFFIRMATIVE",
            "resourceType": "",
        }
        self.realm_client.create_client_authz_resource_based_permission(client_id, permission, True)

    def get_group_user_count(self, group_id, search):
        sql = """SELECT COUNT
    ( ugs.user_id )
FROM
    user_group_membership ugs
    LEFT JOIN user_entity userobj ON userobj."id" = ugs.user_id
WHERE
    ugs.group_id = %(group_id)s
and userobj.username like %(username)s"""
        return_data = SQLExecute.execute_sql(sql, {"group_id": group_id, "username": f"%{search}%"})
        return return_data[0].get("count", 0) if return_data else 0

    def get_group_users(self, group_id, query_params):
        sql = """SELECT
  ue.id, ue.email, ue.first_name as firstname, ue.last_name as lastname, ue.username
FROM
  user_entity ue
  JOIN user_group_membership ugm ON ue.ID = ugm.user_id
WHERE
  ugm.group_id = %(group_id)s
and
  ue.username like %(username)s
  order by created_timestamp
"""
        params = {
            "group_id": group_id,
            "username": f"%{query_params['search']}%",
        }
        if "first" in query_params:
            sql += " OFFSET %(offset)s LIMIT %(limit)s"
            params.update({"offset": query_params["first"], "limit": query_params["max"]})
        return_data = SQLExecute.execute_sql(sql, params)
        return [
            {
                "id": i["id"],
                "email": i["email"],
                "firstName": i["firstname"],
                "lastName": i["lastname"],
                "username": i["username"],
            }
            for i in return_data
        ]

    def get_role_users(self, role_id, query_params):
        sql = """SELECT
  ue.id, ue.email, ue.first_name as firstname, ue.last_name as lastname, ue.username
FROM
  user_entity ue
  JOIN user_role_mapping ugm ON ue.ID = ugm.user_id
WHERE
  ugm.role_id = %(role_id)s
and
  ue.username like %(username)s
  order by created_timestamp
"""
        params = {
            "role_id": role_id,
            "username": f"%{query_params['search']}%",
        }
        if "first" in query_params:
            sql += " OFFSET %(offset)s LIMIT %(limit)s"
            params.update({"offset": query_params["first"], "limit": query_params["max"]})
        return_data = SQLExecute.execute_sql(sql, params)
        return [
            {
                "id": i["id"],
                "email": i["email"],
                "firstName": i["firstname"],
                "lastName": i["lastname"],
                "username": i["username"],
            }
            for i in return_data
        ]
