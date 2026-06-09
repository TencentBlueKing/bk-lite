from apps.cmdb.models.change_record import *  # noqa
from apps.cmdb.models.show_field import *  # noqa
from apps.cmdb.models.collect_model import *  # noqa
from apps.cmdb.models.config_file_version import *  # noqa
from apps.cmdb.models.file_object import *  # noqa
from apps.cmdb.models.field_group import *  # noqa
from apps.cmdb.models.user_personal_config import *  # noqa
from apps.cmdb.models.public_enum_library import *  # noqa
from apps.cmdb.models.subscription_rule import *  # noqa
from apps.cmdb.models.node_mgmt_sync import *  # noqa
from apps.cmdb.models.collect_task_credential_hit import *  # noqa

try:
    enterprise_models = __import__("apps.cmdb.enterprise.models", fromlist=["*"])
    for _name in dir(enterprise_models):
        if _name.startswith("_"):
            continue
        globals()[_name] = getattr(enterprise_models, _name)
except ModuleNotFoundError as exc:
    if exc.name not in {"apps.cmdb.enterprise", "apps.cmdb.enterprise.models"}:
        raise
    from apps.cmdb.models.custom_reporting import *  # noqa
