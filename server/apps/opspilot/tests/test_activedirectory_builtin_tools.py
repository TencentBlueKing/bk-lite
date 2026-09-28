"""Active Directory 内置工具：schema / SQL 引擎 / builtin 挂载。"""

from __future__ import annotations

import pytest

from apps.opspilot.metis.llm.tools.activedirectory import schema as ad_schema
from apps.opspilot.metis.llm.tools.activedirectory.sql_engine import execute_select, parse_select
from apps.opspilot.services import builtin_tools

pytestmark = pytest.mark.unit


class FakeEntry:
    def __init__(self, **attrs):
        self.entry_attributes_as_dict = attrs


def _searcher_factory(dataset):
    """dataset: {object_filter_substr: [FakeEntry, ...]}"""

    def searcher(base_dn, search_filter, attrs, size_limit):
        _ = (base_dn, attrs, size_limit)
        for key, entries in dataset.items():
            if key in search_filter:
                return entries
        return []

    return searcher


class TestSchema:
    def test_core_tables_exist(self):
        names = set(ad_schema.list_table_names())
        assert {"User", "Group", "Computer", "Contact", "Organization"} <= names

    def test_get_table_case_insensitive(self):
        assert ad_schema.get_table("user").name == "User"

    def test_unknown_table_raises(self):
        with pytest.raises(KeyError):
            ad_schema.get_table("Nope")


class TestSqlParser:
    def test_parse_basic_select(self):
        q = parse_select("SELECT SAMAccountName, Mail FROM User WHERE Department = 'IT' ORDER BY SAMAccountName LIMIT 10")
        assert q.from_table == "User"
        assert "SAMAccountName" in q.columns
        assert q.where == "Department = 'IT'"
        assert q.limit == 10
        assert q.order_by[0][0] == "SAMAccountName"

    def test_parse_join(self):
        q = parse_select("SELECT u.SAMAccountName, g.CN FROM User u " "INNER JOIN Group g ON u.DN = g.Member WHERE u.Department = 'IT' LIMIT 5")
        assert q.from_alias == "u"
        assert len(q.joins) == 1
        assert q.joins[0].join_type == "INNER"
        assert q.joins[0].table == "Group"

    def test_reject_write(self):
        with pytest.raises(ValueError):
            parse_select("DELETE FROM User")


class TestSqlEngine:
    def test_select_where_like_limit(self):
        users = [
            FakeEntry(sAMAccountName="alice", mail="a@x.com", department="IT", distinguishedName="CN=alice"),
            FakeEntry(sAMAccountName="bob", mail="b@x.com", department="HR", distinguishedName="CN=bob"),
            FakeEntry(sAMAccountName="admin", mail="admin@x.com", department="IT", distinguishedName="CN=admin"),
        ]
        searcher = _searcher_factory({"objectCategory=person": users})
        cols, rows = execute_select(
            "SELECT SAMAccountName, Mail FROM User WHERE Department = 'IT' AND SAMAccountName LIKE 'a%' ORDER BY SAMAccountName",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )
        assert cols == ["SAMAccountName", "Mail"]
        assert [r["SAMAccountName"] for r in rows] == ["admin", "alice"]

    def test_left_join(self):
        users = [
            FakeEntry(sAMAccountName="alice", distinguishedName="CN=alice,DC=x", department="IT"),
        ]
        groups = [
            FakeEntry(cn="vpn", member="CN=alice,DC=x", distinguishedName="CN=vpn,DC=x"),
            FakeEntry(cn="other", member="CN=bob,DC=x", distinguishedName="CN=other,DC=x"),
        ]
        searcher = _searcher_factory(
            {
                "objectCategory=person": users,
                "objectClass=group": groups,
            }
        )
        cols, rows = execute_select(
            "SELECT u.SAMAccountName, g.CN FROM `User` u LEFT JOIN `Group` g ON u.DN = g.Member",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )
        assert "SAMAccountName" in cols[0] or cols[0].endswith("SAMAccountName") or "SAMAccountName" in cols
        assert any(r.get("CN") == "vpn" or r.get("g.CN") == "vpn" for r in rows)

    def test_group_by_count(self):
        users = [
            FakeEntry(sAMAccountName="a", department="IT", distinguishedName="CN=a"),
            FakeEntry(sAMAccountName="b", department="IT", distinguishedName="CN=b"),
            FakeEntry(sAMAccountName="c", department="HR", distinguishedName="CN=c"),
        ]
        searcher = _searcher_factory({"objectCategory=person": users})
        cols, rows = execute_select(
            "SELECT Department, COUNT(*) AS cnt FROM User GROUP BY Department ORDER BY Department",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )
        by_dept = {r["Department"]: r["cnt"] for r in rows}
        assert by_dept["HR"] == 1
        assert by_dept["IT"] == 2


class FakeLoader:
    def __init__(self, mapping=None):
        self._m = mapping or {}

    def get(self, key):
        return self._m.get(key, "")


class TestBuiltinWiring:
    def test_build_builtin_activedirectory_tool(self):
        data = builtin_tools.build_builtin_activedirectory_tool(FakeLoader())
        assert data["id"] == builtin_tools.BUILTIN_ACTIVEDIRECTORY_TOOL_ID
        assert data["name"] == "activedirectory"
        assert data["params"]["url"] == "langchain:activedirectory"
        names = [t["name"] for t in data["tools"]]
        assert "activedirectory_get_tables" in names
        assert "activedirectory_get_columns" in names
        assert "activedirectory_run_query" in names

    def test_tools_loader_discovers_ad_tools(self):
        from apps.opspilot.metis.llm.tools.tools_loader import ToolsLoader

        tools = ToolsLoader.load_tools("langchain:activedirectory")
        names = {t.name for t in tools}
        assert "activedirectory_get_tables" in names
        assert "activedirectory_get_columns" in names
        assert "activedirectory_run_query" in names


class TestAdConnectionProbe:
    def test_test_ad_instance_requires_fields(self):
        from apps.opspilot.metis.llm.tools.activedirectory.connection import test_ad_instance

        with pytest.raises(ValueError, match="缺少连接参数"):
            test_ad_instance({"host": "dc.example.com"})

    def test_test_ad_instance_binds(self, mocker):
        from apps.opspilot.metis.llm.tools.activedirectory import connection as ad_conn

        fake_conn = mocker.Mock()
        mocker.patch.object(ad_conn, "get_ad_connection_from_item", return_value=fake_conn)
        unbind = mocker.patch.object(ad_conn, "safe_unbind")

        assert (
            ad_conn.test_ad_instance(
                {
                    "host": "dc.example.com",
                    "bind_dn": "CN=a,DC=x",
                    "bind_password": "p",
                    "base_dn": "DC=x",
                }
            )
            is True
        )
        unbind.assert_called_once_with(fake_conn)
