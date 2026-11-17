"""从公开工具到 SDK 连接边界验证多实例路由，不连接外部服务。"""

import importlib
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch

import pytest
from langchain_core.tools import StructuredTool

pytestmark = pytest.mark.unit
ROOT = "apps.opspilot.metis.llm.tools"


class ConnectionReached(BaseException):
    """在连接边界停止，避免被工具的业务错误处理吞掉。"""


def instance_config(category, default="one"):
    prefix = {"elasticsearch": "es", "activedirectory": "ad"}.get(category, category)
    instances = []
    for ident, name in (("one", "first"), ("two", "second")):
        instances.append(
            {
                "id": ident,
                "name": name,
                "host": f"{name}.invalid",
                "port": 5432,
                "database": "audit",
                "user": "audit",
                "password": "",
                "jenkins_url": f"https://{name}.invalid",
                "url": f"https://{name}.invalid",
                "bind_dn": "cn=audit",
                "base_dn": "dc=audit",
                "bind_password": "synthetic-test-password",
            }
        )
    return {"configurable": {f"{prefix}_instances": instances, f"{prefix}_default_instance_id": default}}


def load_category(category):
    if category == "mssql":
        pytest.importorskip("pyodbc", reason="本机缺少 pyodbc/unixodbc", exc_type=ImportError)
    return importlib.import_module(f"{ROOT}.{category}")


def tool_arguments(tool):
    schema = tool.get_input_schema().model_json_schema()
    arguments = {}
    for name in schema.get("required", []):
        if name == "config":
            continue
        field = schema["properties"][name]
        kind = field.get("type")
        arguments[name] = {"object": {}, "array": [], "integer": 1, "boolean": True}.get(kind, "audit")
    if "sql" in tool.args:
        arguments["sql"] = "SELECT 1 AS value"
    if tool.name == "execute_fallback_readonly_sql":
        arguments["sql"] = "SELECT TOP 1 id FROM dbo.audit"
    if tool.name == "get_sample_data":
        arguments["columns"] = "id,name"
    if "confirm" in tool.args:
        arguments["confirm"] = True
    if "parameters" in tool.args:
        arguments["parameters"] = {}
    return arguments


def connection_boundary(stack, category):
    if category == "postgres":
        target = f"{ROOT}.postgres.utils.psycopg2.connect"
    elif category == "mssql":
        stack.enter_context(patch(f"{ROOT}.mssql.utils.get_available_driver", return_value="audit driver"))
        stack.enter_context(patch(f"{ROOT}.mssql.connection.get_available_driver", return_value="audit driver"))
        target = f"{ROOT}.mssql.utils.pyodbc.connect"
    elif category == "jenkins":
        target = "jenkins.Jenkins"
    else:
        target = f"{ROOT}.elasticsearch.connection.Elasticsearch"
    return stack.enter_context(patch(target, side_effect=ConnectionReached))


def target_address(category, connect):
    args, kwargs = connect.call_args
    if category == "postgres":
        return kwargs["host"]
    if category == "elasticsearch":
        return str(kwargs["hosts"])
    return args[0]


@pytest.mark.parametrize("category", ["postgres", "mssql", "jenkins", "elasticsearch"])
@pytest.mark.parametrize("selection", [{"instance_name": "second"}, {"instance_id": "two"}, {"instance_name": "first", "instance_id": "two"}])
def test_every_public_tool_connects_only_to_selected_instance(category, selection):
    module = load_category(category)
    public_tools = [value for value in vars(module).values() if isinstance(value, StructuredTool)]
    assert public_tools
    config = instance_config(category)
    original = deepcopy(config)
    for tool in public_tools:
        assert {"instance_name", "instance_id"} <= set(tool.args), tool.name
        with ExitStack() as stack:
            connect = connection_boundary(stack, category)
            try:
                result = tool.invoke({**tool_arguments(tool), **selection}, config=config)
            except ConnectionReached:
                pass
            else:
                pytest.fail(f"{tool.name} did not reach connection: {result}")
            assert "second.invalid" in target_address(category, connect), tool.name
            assert connect.call_count == 1, tool.name
        assert config == original


@pytest.mark.parametrize(
    "category,tool_name",
    [
        ("postgres", "get_current_database_info"),
        ("mssql", "get_current_database_info"),
        ("jenkins", "list_jenkins_jobs"),
        ("elasticsearch", "es_info"),
    ],
)
def test_unspecified_instance_uses_configured_default(category, tool_name):
    tool = getattr(load_category(category), tool_name)
    with ExitStack() as stack:
        connect = connection_boundary(stack, category)
        with pytest.raises(ConnectionReached):
            tool.invoke({}, config=instance_config(category, default="two"))
        assert "second.invalid" in target_address(category, connect)
        assert connect.call_count == 1


@pytest.mark.parametrize(
    "category,tool_name",
    [
        ("postgres", "get_current_database_info"),
        ("mssql", "get_current_database_info"),
        ("jenkins", "list_jenkins_jobs"),
        ("elasticsearch", "es_info"),
    ],
)
@pytest.mark.parametrize("selection", [{"instance_name": "missing"}, {"instance_id": "missing"}])
def test_unknown_instance_never_connects(category, tool_name, selection):
    tool = getattr(load_category(category), tool_name)
    with ExitStack() as stack:
        connect = connection_boundary(stack, category)
        try:
            result = tool.invoke(selection, config=instance_config(category))
        except ValueError as exc:
            result = str(exc)
        assert not connect.called
        assert "not found" in str(result).lower()


@pytest.mark.parametrize("selection", [{"instance_name": "missing"}, {"instance_id": "missing"}])
def test_ad_unknown_instance_never_fans_out(selection):
    module = load_category("activedirectory")
    with patch(f"{ROOT}.activedirectory.tools.get_ad_connection_from_item") as connect:
        result = module.activedirectory_get_tables.invoke(selection, config=instance_config("activedirectory"))
    connect.assert_not_called()
    assert "not found" in result.lower()


@pytest.mark.parametrize("category", ["postgres", "mssql"])
def test_database_override_uses_selected_instance_once_without_mutating_config(category):
    load_category(category)
    utils = importlib.import_module(f"{ROOT}.{category}.utils")
    config = instance_config(category)
    original = deepcopy(config)
    with ExitStack() as stack:
        connect = connection_boundary(stack, category)
        connect.side_effect = None
        connection = utils.get_db_connection(config, database="reporting", instance_id="two")
        assert connection is connect.return_value
        assert connect.call_count == 1
        assert "second.invalid" in target_address(category, connect)
        if category == "postgres":
            assert connect.call_args.kwargs["database"] == "reporting"
        else:
            assert "DATABASE=reporting;" in connect.call_args.args[0]
            assert "ApplicationIntent=ReadOnly" in connect.call_args.args[0]
        connection.close.assert_not_called()
    assert config == original


@pytest.mark.parametrize("category", ["postgres", "mssql", "jenkins", "elasticsearch"])
def test_legacy_flat_configuration_still_connects(category):
    load_category(category)
    fields = instance_config(category)["configurable"]
    item = next(value for key, value in fields.items() if key.endswith("_instances"))[0]
    if category == "elasticsearch":
        config = {"configurable": {"url": item["url"]}}
    else:
        config = {"configurable": item}
    with ExitStack() as stack:
        connect = connection_boundary(stack, category)
        if category in ("postgres", "mssql"):
            call = importlib.import_module(f"{ROOT}.{category}.utils").get_db_connection
        elif category == "jenkins":
            call = importlib.import_module(f"{ROOT}.jenkins.build").get_client
        else:
            call = importlib.import_module(f"{ROOT}.elasticsearch.connection").get_es_client
        with pytest.raises(ConnectionReached):
            call(config)
        assert "first.invalid" in target_address(category, connect)


@pytest.mark.parametrize("category", ["postgres", "mssql", "jenkins", "elasticsearch"])
def test_legacy_configuration_rejects_explicit_unknown_target(category):
    load_category(category)
    with ExitStack() as stack:
        connect = connection_boundary(stack, category)
        if category in ("postgres", "mssql"):
            call = importlib.import_module(f"{ROOT}.{category}.utils").get_db_connection
        elif category == "jenkins":
            call = importlib.import_module(f"{ROOT}.jenkins.build").get_client
        else:
            call = importlib.import_module(f"{ROOT}.elasticsearch.connection").get_es_client
        with pytest.raises(ValueError, match="selection is unavailable"):
            call({"configurable": {}}, instance_name="missing")
        connect.assert_not_called()


@pytest.mark.parametrize("selection", [{"instance_name": "second"}, {"instance_id": "two"}])
def test_ad_valid_instance_still_selects_only_that_domain(selection):
    module = load_category("activedirectory")
    with patch(f"{ROOT}.activedirectory.tools.get_ad_connection_from_item", side_effect=ConnectionReached) as connect:
        with pytest.raises(ConnectionReached):
            module.activedirectory_get_tables.invoke(selection, config=instance_config("activedirectory"))
    assert connect.call_args.args[0]["config"]["host"] == "second.invalid"
    assert connect.call_count == 1
