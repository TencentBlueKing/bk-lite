from apps.core.utils.loader import LanguageLoader

BUILTIN_MONITOR_TOOL_ID = -6
BUILTIN_MONITOR_TOOL_NAME = "monitor"

BUILTIN_ATTACHMENT_FILE_TOOL_ID = -5
BUILTIN_ATTACHMENT_FILE_TOOL_NAME = "attachment_file"

BUILTIN_REDIS_TOOL_ID = -1
BUILTIN_REDIS_TOOL_NAME = "redis"

BUILTIN_MYSQL_TOOL_ID = -2
BUILTIN_MYSQL_TOOL_NAME = "mysql"

BUILTIN_ORACLE_TOOL_ID = -3
BUILTIN_ORACLE_TOOL_NAME = "oracle"

BUILTIN_MSSQL_TOOL_ID = -4
BUILTIN_MSSQL_TOOL_NAME = "mssql"


def _get_display_name(loader: LanguageLoader, tool_name: str, default: str) -> str:
    """获取工具的展示名称（中英文）。

    复用 language 目录下的 yaml 翻译映射（``tools.{tool_name}.name``），
    未配置翻译时回退到传入的 default（英文展示名）。
    """
    return loader.get(f"tools.{tool_name}.name") or default


def _build_kwargs_from_params(constructor_params):
    return [
        {
            "key": item["name"],
            "value": "",
            "type": item["type"],
            "isRequired": item["required"],
            "description": item["description"],
        }
        for item in constructor_params
    ]


def _build_sub_tools(tool_name, exports, loader: LanguageLoader):
    sub_tools = []
    for name in exports:
        if name == "CONSTRUCTOR_PARAMS":
            continue
        sub_tools.append(
            {
                "name": name,
                "description": loader.get(f"tools.{tool_name}.tools.{name}.description") or "",
            }
        )
    return sub_tools


def build_builtin_monitor_tool(loader: LanguageLoader):
    from apps.opspilot.metis.llm.tools.monitor import CONSTRUCTOR_PARAMS as monitor_constructor_params
    from apps.opspilot.metis.llm.tools.monitor import __all__ as monitor_exports

    description = loader.get(f"tools.{BUILTIN_MONITOR_TOOL_NAME}.description") or "Monitor built-in tool"
    return {
        "id": BUILTIN_MONITOR_TOOL_ID,
        "name": BUILTIN_MONITOR_TOOL_NAME,
        "display_name": _get_display_name(loader, BUILTIN_MONITOR_TOOL_NAME, "Monitor"),
        "description": description,
        "description_tr": description,
        "icon": "gongjuji",
        "team": [],
        "tags": [],
        "params": {
            "name": BUILTIN_MONITOR_TOOL_NAME,
            "url": f"langchain:{BUILTIN_MONITOR_TOOL_NAME}",
            "kwargs": _build_kwargs_from_params(monitor_constructor_params),
            "enable_auth": False,
            "auth_token": "",
        },
        "is_build_in": True,
        "tools": _build_sub_tools(BUILTIN_MONITOR_TOOL_NAME, monitor_exports, loader),
    }


def build_builtin_monitor_runtime_tool(tool_kwargs):
    return {
        "name": BUILTIN_MONITOR_TOOL_NAME,
        "url": f"langchain:{BUILTIN_MONITOR_TOOL_NAME}",
        "enable_auth": False,
        "auth_token": "",
        "extra_param_prompt": tool_kwargs or {},
    }


def build_builtin_attachment_file_tool(loader: LanguageLoader):
    from apps.opspilot.metis.llm.tools.attachment import CONSTRUCTOR_PARAMS as attachment_constructor_params
    from apps.opspilot.metis.llm.tools.attachment import __all__ as attachment_exports

    description = loader.get(f"tools.{BUILTIN_ATTACHMENT_FILE_TOOL_NAME}.description") or "Workflow attachment built-in tool"
    return {
        "id": BUILTIN_ATTACHMENT_FILE_TOOL_ID,
        "name": BUILTIN_ATTACHMENT_FILE_TOOL_NAME,
        "display_name": _get_display_name(loader, BUILTIN_ATTACHMENT_FILE_TOOL_NAME, "Attachment File"),
        "description": description,
        "description_tr": description,
        "icon": "gongjuji",
        "team": [],
        "tags": [],
        "params": {
            "name": BUILTIN_ATTACHMENT_FILE_TOOL_NAME,
            "url": f"langchain:{BUILTIN_ATTACHMENT_FILE_TOOL_NAME}",
            "kwargs": _build_kwargs_from_params(attachment_constructor_params),
            "enable_auth": False,
            "auth_token": "",
        },
        "is_build_in": True,
        "tools": _build_sub_tools(BUILTIN_ATTACHMENT_FILE_TOOL_NAME, attachment_exports, loader),
    }


def build_builtin_attachment_file_runtime_tool(tool_kwargs):
    return {
        "name": BUILTIN_ATTACHMENT_FILE_TOOL_NAME,
        "url": f"langchain:{BUILTIN_ATTACHMENT_FILE_TOOL_NAME}",
        "enable_auth": False,
        "auth_token": "",
        "extra_tools_prompt": "",
        "extra_param_prompt": tool_kwargs or {},
    }


def build_builtin_redis_tool(loader: LanguageLoader):
    from apps.opspilot.metis.llm.tools.redis import CONSTRUCTOR_PARAMS as redis_constructor_params
    from apps.opspilot.metis.llm.tools.redis import __all__ as redis_exports

    description = loader.get(f"tools.{BUILTIN_REDIS_TOOL_NAME}.description") or "Redis built-in tool"
    return {
        "id": BUILTIN_REDIS_TOOL_ID,
        "name": BUILTIN_REDIS_TOOL_NAME,
        "display_name": _get_display_name(loader, BUILTIN_REDIS_TOOL_NAME, "Redis"),
        "description": description,
        "description_tr": description,
        "icon": "gongjuji",
        "team": [],
        "tags": [],
        "params": {
            "name": BUILTIN_REDIS_TOOL_NAME,
            "url": f"langchain:{BUILTIN_REDIS_TOOL_NAME}",
            "kwargs": _build_kwargs_from_params(redis_constructor_params),
            "enable_auth": False,
            "auth_token": "",
        },
        "is_build_in": True,
        "tools": _build_sub_tools(BUILTIN_REDIS_TOOL_NAME, redis_exports, loader),
    }


def build_builtin_redis_runtime_tool(tool_kwargs):
    from apps.opspilot.metis.llm.tools.redis.connection import get_redis_instances_prompt

    return {
        "name": BUILTIN_REDIS_TOOL_NAME,
        "url": f"langchain:{BUILTIN_REDIS_TOOL_NAME}",
        "enable_auth": False,
        "auth_token": "",
        "extra_tools_prompt": get_redis_instances_prompt(tool_kwargs),
    }


def build_builtin_mysql_tool(loader: LanguageLoader):
    from apps.opspilot.metis.llm.tools.mysql import CONSTRUCTOR_PARAMS as mysql_constructor_params
    from apps.opspilot.metis.llm.tools.mysql import __all__ as mysql_exports

    description = loader.get(f"tools.{BUILTIN_MYSQL_TOOL_NAME}.description") or "MySQL built-in tool"
    return {
        "id": BUILTIN_MYSQL_TOOL_ID,
        "name": BUILTIN_MYSQL_TOOL_NAME,
        "display_name": _get_display_name(loader, BUILTIN_MYSQL_TOOL_NAME, "MySQL"),
        "description": description,
        "description_tr": description,
        "icon": "gongjuji",
        "team": [],
        "tags": [],
        "params": {
            "name": BUILTIN_MYSQL_TOOL_NAME,
            "url": f"langchain:{BUILTIN_MYSQL_TOOL_NAME}",
            "kwargs": _build_kwargs_from_params(mysql_constructor_params),
            "enable_auth": False,
            "auth_token": "",
        },
        "is_build_in": True,
        "tools": _build_sub_tools(BUILTIN_MYSQL_TOOL_NAME, mysql_exports, loader),
    }


def build_builtin_mysql_runtime_tool(tool_kwargs):
    from apps.opspilot.metis.llm.tools.mysql.connection import get_mysql_instances_prompt

    return {
        "name": BUILTIN_MYSQL_TOOL_NAME,
        "url": f"langchain:{BUILTIN_MYSQL_TOOL_NAME}",
        "enable_auth": False,
        "auth_token": "",
        "extra_tools_prompt": get_mysql_instances_prompt(tool_kwargs),
    }


def build_builtin_oracle_tool(loader: LanguageLoader):
    from apps.opspilot.metis.llm.tools.oracle import CONSTRUCTOR_PARAMS as oracle_constructor_params
    from apps.opspilot.metis.llm.tools.oracle import __all__ as oracle_exports

    description = loader.get(f"tools.{BUILTIN_ORACLE_TOOL_NAME}.description") or "Oracle built-in tool"
    return {
        "id": BUILTIN_ORACLE_TOOL_ID,
        "name": BUILTIN_ORACLE_TOOL_NAME,
        "display_name": _get_display_name(loader, BUILTIN_ORACLE_TOOL_NAME, "Oracle"),
        "description": description,
        "description_tr": description,
        "icon": "gongjuji",
        "team": [],
        "tags": [],
        "params": {
            "name": BUILTIN_ORACLE_TOOL_NAME,
            "url": f"langchain:{BUILTIN_ORACLE_TOOL_NAME}",
            "kwargs": _build_kwargs_from_params(oracle_constructor_params),
            "enable_auth": False,
            "auth_token": "",
        },
        "is_build_in": True,
        "tools": _build_sub_tools(BUILTIN_ORACLE_TOOL_NAME, oracle_exports, loader),
    }


def build_builtin_oracle_runtime_tool(tool_kwargs):
    from apps.opspilot.metis.llm.tools.oracle.connection import get_oracle_instances_prompt

    return {
        "name": BUILTIN_ORACLE_TOOL_NAME,
        "url": f"langchain:{BUILTIN_ORACLE_TOOL_NAME}",
        "enable_auth": False,
        "auth_token": "",
        "extra_tools_prompt": get_oracle_instances_prompt(tool_kwargs),
    }


def build_builtin_mssql_tool(loader: LanguageLoader):
    from apps.opspilot.metis.llm.tools.mssql import CONSTRUCTOR_PARAMS as mssql_constructor_params
    from apps.opspilot.metis.llm.tools.mssql import __all__ as mssql_exports

    description = loader.get(f"tools.{BUILTIN_MSSQL_TOOL_NAME}.description") or "MSSQL built-in tool"
    return {
        "id": BUILTIN_MSSQL_TOOL_ID,
        "name": BUILTIN_MSSQL_TOOL_NAME,
        "display_name": _get_display_name(loader, BUILTIN_MSSQL_TOOL_NAME, "MSSQL"),
        "description": description,
        "description_tr": description,
        "icon": "gongjuji",
        "team": [],
        "tags": [],
        "params": {
            "name": BUILTIN_MSSQL_TOOL_NAME,
            "url": f"langchain:{BUILTIN_MSSQL_TOOL_NAME}",
            "kwargs": _build_kwargs_from_params(mssql_constructor_params),
            "enable_auth": False,
            "auth_token": "",
        },
        "is_build_in": True,
        "tools": _build_sub_tools(BUILTIN_MSSQL_TOOL_NAME, mssql_exports, loader),
    }


def build_builtin_mssql_runtime_tool(tool_kwargs):
    from apps.opspilot.metis.llm.tools.mssql.connection import get_mssql_instances_prompt

    return {
        "name": BUILTIN_MSSQL_TOOL_NAME,
        "url": f"langchain:{BUILTIN_MSSQL_TOOL_NAME}",
        "enable_auth": False,
        "auth_token": "",
        "extra_tools_prompt": get_mssql_instances_prompt(tool_kwargs),
    }
