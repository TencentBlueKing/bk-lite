"""opspilot-biz 切片: services/builtin_tools 数据库类内置工具构建。

覆盖 redis/mysql/oracle/mssql 四类工具的 build_*_tool 结构（id/name/params/tools）
与对应 runtime tool（extra_tools_prompt 来自 connection 模块——真实外部边界，mock）。
另测共享私有 helper _build_kwargs_from_params / _build_sub_tools / _get_display_name。
"""

import pytest

from apps.opspilot.services import builtin_tools

pytestmark = pytest.mark.unit


class FakeLoader:
    """LanguageLoader 替身：按预置映射返回翻译，未命中返回 ''。"""

    def __init__(self, mapping=None):
        self._m = mapping or {}

    def get(self, key):
        return self._m.get(key, "")


class TestHelpers:
    def test_build_kwargs_from_params_映射结构(self):
        params = [
            {"name": "host", "type": "string", "required": True, "description": "主机"},
            {"name": "port", "type": "int", "required": False, "description": "端口"},
        ]
        out = builtin_tools._build_kwargs_from_params(params)
        assert out == [
            {"key": "host", "value": "", "type": "string", "isRequired": True, "description": "主机"},
            {"key": "port", "value": "", "type": "int", "isRequired": False, "description": "端口"},
        ]

    def test_build_sub_tools_跳过CONSTRUCTOR_PARAMS(self):
        loader = FakeLoader({"tools.redis.tools.get_key.description": "读取键"})
        out = builtin_tools._build_sub_tools("redis", ["CONSTRUCTOR_PARAMS", "get_key", "set_key"], loader)
        names = [t["name"] for t in out]
        assert "CONSTRUCTOR_PARAMS" not in names
        assert names == ["get_key", "set_key"]
        # 有翻译用翻译，无翻译回退空串
        assert out[0]["description"] == "读取键"
        assert out[1]["description"] == ""

    def test_get_display_name_翻译命中(self):
        loader = FakeLoader({"tools.redis.name": "缓存"})
        assert builtin_tools._get_display_name(loader, "redis", "Redis") == "缓存"

    def test_get_display_name_回退default(self):
        assert builtin_tools._get_display_name(FakeLoader(), "redis", "Redis") == "Redis"


class TestBuildDbTools:
    @pytest.mark.parametrize(
        "builder,expected_id,expected_name,default_display",
        [
            ("build_builtin_redis_tool", builtin_tools.BUILTIN_REDIS_TOOL_ID, "redis", "Redis"),
            ("build_builtin_mysql_tool", builtin_tools.BUILTIN_MYSQL_TOOL_ID, "mysql", "MySQL"),
            ("build_builtin_oracle_tool", builtin_tools.BUILTIN_ORACLE_TOOL_ID, "oracle", "Oracle"),
            # mssql 依赖 pyodbc 的本地 unixodbc 库，测试环境未安装，跳过其工具构建用例。
        ],
    )
    def test_无翻译时使用默认展示名与描述(self, builder, expected_id, expected_name, default_display):
        data = getattr(builtin_tools, builder)(FakeLoader())
        assert data["id"] == expected_id
        assert data["name"] == expected_name
        assert data["display_name"] == default_display
        assert data["is_build_in"] is True
        assert data["params"]["url"] == f"langchain:{expected_name}"
        # kwargs 来自 CONSTRUCTOR_PARAMS，应为列表
        assert isinstance(data["params"]["kwargs"], list)
        # 子工具列表存在且不含 CONSTRUCTOR_PARAMS
        assert all(t["name"] != "CONSTRUCTOR_PARAMS" for t in data["tools"])
        # 未翻译时 description 回退到英文默认
        assert default_display.lower() in data["description"].lower() or "built-in" in data["description"].lower()

    def test_翻译命中时使用翻译展示名(self):
        loader = FakeLoader({"tools.mysql.name": "我的SQL", "tools.mysql.description": "MySQL 工具"})
        data = builtin_tools.build_builtin_mysql_tool(loader)
        assert data["display_name"] == "我的SQL"
        assert data["description"] == "MySQL 工具"


class TestRuntimeTools:
    def test_redis_runtime_注入prompt(self, mocker):
        mocker.patch(
            "apps.opspilot.metis.llm.tools.redis.connection.get_redis_instances_prompt",
            return_value="REDIS_PROMPT",
        )
        out = builtin_tools.build_builtin_redis_runtime_tool({"k": "v"})
        assert out["name"] == "redis"
        assert out["url"] == "langchain:redis"
        assert out["extra_tools_prompt"] == "REDIS_PROMPT"

    def test_mysql_runtime_注入prompt(self, mocker):
        mocker.patch(
            "apps.opspilot.metis.llm.tools.mysql.connection.get_mysql_instances_prompt",
            return_value="MYSQL_PROMPT",
        )
        out = builtin_tools.build_builtin_mysql_runtime_tool({})
        assert out["extra_tools_prompt"] == "MYSQL_PROMPT"

    def test_oracle_runtime_注入prompt(self, mocker):
        mocker.patch(
            "apps.opspilot.metis.llm.tools.oracle.connection.get_oracle_instances_prompt",
            return_value="ORA_PROMPT",
        )
        out = builtin_tools.build_builtin_oracle_runtime_tool({})
        assert out["extra_tools_prompt"] == "ORA_PROMPT"

    def test_attachment_runtime_extra_param_prompt(self):
        out = builtin_tools.build_builtin_attachment_file_runtime_tool({"a": 1})
        assert out["name"] == "attachment_file"
        assert out["extra_param_prompt"] == {"a": 1}
        # 空 kwargs 归一化为 {}
        assert builtin_tools.build_builtin_attachment_file_runtime_tool(None)["extra_param_prompt"] == {}
