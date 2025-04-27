import os

BUILT_IN_ROLES = {
    f"default-roles-{os.getenv('KEYCLOAK_REALM')}",
    "default-roles-master",
    "uma_authorization",
    "offline_access",
}
