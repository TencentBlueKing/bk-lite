"""Active Directory 内置工具：schema / SQL 引擎 / builtin 挂载。"""

from __future__ import annotations

import logging
import ssl

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

    def test_count_star_without_group_by_returns_one_number(self):
        users = [
            FakeEntry(sAMAccountName="a", department="IT", distinguishedName="CN=a"),
            FakeEntry(sAMAccountName="b", department="HR", distinguishedName="CN=b"),
        ]
        searcher = _searcher_factory({"objectCategory=person": users})
        cols, rows = execute_select(
            "SELECT COUNT(*) AS cnt FROM User",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )
        assert cols == ["cnt"]
        assert rows == [{"cnt": 2}]

        filtered_cols, filtered_rows = execute_select(
            "SELECT COUNT(*) AS cnt FROM User WHERE Department = 'IT'",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )
        assert filtered_cols == ["cnt"]
        assert filtered_rows == [{"cnt": 1}]

    def test_like_filter_is_sent_to_the_directory_before_counting(self):
        filters = []

        def searcher(base_dn, search_filter, attrs, size_limit):
            _ = (base_dn, attrs, size_limit)
            filters.append(search_filter)
            if "sAMAccountName=*test*" in search_filter or "cn=*test*" in search_filter:
                return [FakeEntry(sAMAccountName="testuser", cn="test user", distinguishedName="CN=testuser")]
            return [FakeEntry(sAMAccountName=f"user{i}", cn=f"user{i}", distinguishedName=f"CN=user{i}") for i in range(5)]

        cols, rows = execute_select(
            "SELECT COUNT(*) AS cnt FROM User WHERE SAMAccountName LIKE '%test%' OR CN LIKE '%test%'",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )

        assert cols == ["cnt"]
        assert rows == [{"cnt": 1}]
        assert len(filters) == 1
        assert "objectCategory=person" in filters[0]
        assert "sAMAccountName=*test*" in filters[0]
        assert "cn=*test*" in filters[0]
        assert filters[0].startswith("(&")

        blocked = []

        def unfiltered(base_dn, search_filter, attrs, size_limit):
            _ = (base_dn, attrs, size_limit)
            blocked.append(search_filter)
            return [FakeEntry(sAMAccountName="alice", userAccountControl="512", distinguishedName="CN=alice")]

        execute_select(
            "SELECT SAMAccountName FROM User WHERE SAMAccountName LIKE '%a%' OR UserAccountControl > 1",
            base_dn="DC=example,DC=com",
            searcher=unfiltered,
        )
        assert "sAMAccountName=*a*" not in blocked[0]

    def test_join_does_not_push_unqualified_shared_column(self):
        filters = []
        users = [
            FakeEntry(sAMAccountName="bob", name="bob", department="HR", distinguishedName="CN=bob"),
            FakeEntry(sAMAccountName="alice", name="alice", department="IT", distinguishedName="CN=alice"),
        ]
        groups = [
            FakeEntry(cn="admins", name="alice", member="CN=bob", distinguishedName="CN=admins"),
            FakeEntry(cn="vpn", name="vpn", member="CN=alice", distinguishedName="CN=vpn"),
        ]

        def searcher(base_dn, search_filter, attrs, size_limit):
            _ = (base_dn, attrs, size_limit)
            filters.append(search_filter)
            lowered = search_filter.lower()
            if "objectcategory=person" in lowered:
                rows = users
            elif "objectclass=group" in lowered:
                rows = groups
            else:
                return []
            if "(name=" in lowered:
                wanted = lowered.split("(name=", 1)[1].split(")", 1)[0]
                rows = [row for row in rows if str(row.entry_attributes_as_dict.get("name", "")).lower() == wanted]
            if "(department=" in lowered:
                wanted = lowered.split("(department=", 1)[1].split(")", 1)[0]
                rows = [row for row in rows if str(row.entry_attributes_as_dict.get("department", "")).lower() == wanted]
            return rows

        cols, rows = execute_select(
            "SELECT User.SAMAccountName, Group.CN FROM User INNER JOIN Group ON User.DN = Group.Member WHERE Name = 'alice'",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )
        assert cols == ["User.SAMAccountName", "Group.CN"]
        assert rows == [{"User.SAMAccountName": "bob", "Group.CN": "admins"}]
        assert len(filters) == 2
        assert all("(name=" not in item.lower() for item in filters)

        filters.clear()
        qualified_cols, qualified_rows = execute_select(
            "SELECT User.SAMAccountName, Group.CN FROM User INNER JOIN Group ON User.DN = Group.Member WHERE User.Department = 'IT'",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )
        user_filters = [item for item in filters if "objectCategory=person" in item]
        group_filters = [item for item in filters if "objectClass=group" in item]
        assert qualified_cols == ["User.SAMAccountName", "Group.CN"]
        assert qualified_rows == [{"User.SAMAccountName": "alice", "Group.CN": "vpn"}]
        assert len(user_filters) == 1
        assert len(group_filters) == 1
        assert "(department=IT)" in user_filters[0]
        assert "(department=" not in group_filters[0].lower()
        assert "(name=" not in group_filters[0].lower()

        filters.clear()
        _, single_rows = execute_select(
            "SELECT SAMAccountName FROM User WHERE Name = 'alice'",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )
        assert single_rows == [{"SAMAccountName": "alice"}]
        assert len(filters) == 1
        assert "(name=alice)" in filters[0]

    def test_like_underscore_is_not_pushed_to_ldap(self):
        filters = []
        users = [
            FakeEntry(sAMAccountName="alice", department="IT", distinguishedName="CN=alice"),
            FakeEntry(sAMAccountName="abice", department="IT", distinguishedName="CN=abice"),
            FakeEntry(sAMAccountName="axxice", department="HR", distinguishedName="CN=axxice"),
            FakeEntry(sAMAccountName="bob", department="HR", distinguishedName="CN=bob"),
        ]

        def searcher(base_dn, search_filter, attrs, size_limit):
            _ = (base_dn, attrs, size_limit)
            filters.append(search_filter)
            return users

        cols, rows = execute_select(
            "SELECT SAMAccountName FROM User WHERE SAMAccountName LIKE 'a_ice'",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )
        assert cols == ["SAMAccountName"]
        assert [row["SAMAccountName"] for row in rows] == ["alice", "abice"]
        assert "sAMAccountName=" not in filters[0]

        filters.clear()
        _, percent_rows = execute_select(
            "SELECT SAMAccountName FROM User WHERE SAMAccountName LIKE 'a%'",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )
        assert [row["SAMAccountName"] for row in percent_rows] == ["alice", "abice", "axxice"]
        assert "(sAMAccountName=a*)" in filters[0]

        filters.clear()
        execute_select(
            "SELECT SAMAccountName FROM User WHERE Department = 'IT' AND SAMAccountName LIKE 'a_ice'",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )
        assert "(department=IT)" in filters[0]
        assert "sAMAccountName=" not in filters[0]


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


_PASSWORD_SENTINEL = "BIND_PASSWORD_SENTINEL"
_CA_SENTINEL = "CA_PEM_SENTINEL_DO_NOT_LOG"
_CA_PEM = f"-----BEGIN CERTIFICATE-----\n{_CA_SENTINEL}\n-----END CERTIFICATE-----"
_HOST_WITH_BREAK = "dc.example.com\r\ninjected"
_VERIFY_DISABLED_TEMPLATE = "event=ad_ldaps_certificate_verification_disabled instance_id=%s host=%s"


def _ad_config(**overrides):
    config = {
        "id": "ad-1",
        "name": "AD",
        "host": "dc.example.com",
        "port": 636,
        "use_ssl": True,
        "bind_dn": "CN=svc,DC=example,DC=com",
        "bind_password": _PASSWORD_SENTINEL,
        "base_dn": "DC=example,DC=com",
    }
    config.update(overrides)
    return config


def _credential_item(config):
    return {"index": 0, "name": config.get("name") or "AD", "raw": config, "config": config}


def _patch_ldap(mocker):
    tls = mocker.patch("apps.opspilot.metis.llm.tools.activedirectory.connection.Tls")
    server = mocker.patch("apps.opspilot.metis.llm.tools.activedirectory.connection.Server")
    connection = mocker.patch("apps.opspilot.metis.llm.tools.activedirectory.connection.Connection")
    fake_conn = mocker.Mock()
    connection.return_value = fake_conn
    return tls, server, connection, fake_conn


class TestAdLdapsCertificateVerification:
    def test_normalize_and_adapter_default_verify_cert(self):
        from apps.opspilot.metis.llm.tools.activedirectory.connection import (
            AD_INSTANCE_FIELDS,
            ActiveDirectoryCredentialAdapter,
            normalize_ad_instance,
        )

        assert "verify_cert" in AD_INSTANCE_FIELDS
        assert "ca_cert" in AD_INSTANCE_FIELDS
        normalized = normalize_ad_instance(_ad_config())
        assert normalized["verify_cert"] is True
        assert normalized["ca_cert"] == ""
        assert normalized["bind_password"] == _PASSWORD_SENTINEL

        explicit = normalize_ad_instance(_ad_config(verify_cert="false", ca_cert=f"  {_CA_PEM}  "))
        assert explicit["verify_cert"] is False
        assert explicit["ca_cert"] == _CA_PEM

        adapter = ActiveDirectoryCredentialAdapter()
        flat = adapter.build_from_flat_config(
            {
                "ad_host": "dc.example.com",
                "ad_bind_dn": "CN=svc,DC=example,DC=com",
                "ad_bind_password": _PASSWORD_SENTINEL,
                "ad_base_dn": "DC=example,DC=com",
                "ad_verify_cert": "no",
                "ad_ca_cert": _CA_PEM,
            }
        )
        assert flat["verify_cert"] is False
        assert flat["ca_cert"] == _CA_PEM
        assert flat["host"] == "dc.example.com"
        assert flat["bind_password"] == _PASSWORD_SENTINEL

        from_item = adapter.build_from_credential_item(_ad_config(verify_cert=True, ca_cert=_CA_PEM))
        assert from_item["verify_cert"] is True
        assert from_item["ca_cert"] == _CA_PEM

    def test_default_ldaps_requires_certificate(self, mocker, caplog):
        from apps.opspilot.metis.llm.tools.activedirectory.connection import get_ad_connection_from_item

        tls, server, connection, fake_conn = _patch_ldap(mocker)
        tls_obj = mocker.Mock()
        tls.return_value = tls_obj
        caplog.set_level(logging.DEBUG, logger="opspilot")

        result = get_ad_connection_from_item(_credential_item(_ad_config()))

        assert result is fake_conn
        tls.assert_called_once_with(validate=ssl.CERT_REQUIRED, version=ssl.PROTOCOL_TLS_CLIENT)
        server.assert_called_once()
        assert server.call_args.kwargs["use_ssl"] is True
        assert server.call_args.kwargs["tls"] is tls_obj
        assert connection.call_args.kwargs["password"] == _PASSWORD_SENTINEL
        assert connection.call_args.kwargs["user"] == "CN=svc,DC=example,DC=com"
        assert not any(record.levelno >= logging.WARNING for record in caplog.records)

    def test_disabled_verification_uses_cert_none_and_omits_secrets(self, mocker, caplog):
        from apps.core.logger import safe_log_value
        from apps.opspilot.metis.llm.tools.activedirectory.connection import get_ad_connection_from_item

        tls, server, connection, fake_conn = _patch_ldap(mocker)
        caplog.set_level(logging.DEBUG, logger="opspilot")
        config = _ad_config(host=_HOST_WITH_BREAK, verify_cert=False, ca_cert=_CA_PEM)

        result = get_ad_connection_from_item(_credential_item(config))

        assert result is fake_conn
        tls.assert_called_once_with(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLS_CLIENT)
        assert server.call_args.args[0] == _HOST_WITH_BREAK
        assert connection.call_args.kwargs["password"] == _PASSWORD_SENTINEL
        warnings = [record for record in caplog.records if record.msg == _VERIFY_DISABLED_TEMPLATE]
        assert len(warnings) == 1
        record = warnings[0]
        assert record.name == "opspilot"
        assert record.levelno == logging.WARNING
        assert record.args == (safe_log_value("ad-1"), safe_log_value(_HOST_WITH_BREAK))
        assert record.exc_info is None
        assert not any(item.levelno >= logging.ERROR for item in caplog.records)
        formatter = logging.Formatter("%(levelname)s %(name)s %(message)s")
        rendered = record.getMessage()
        formatted = formatter.format(record)
        assert rendered == "event=ad_ldaps_certificate_verification_disabled instance_id=ad-1 host=dc.example.com\\r\\ninjected"
        assert "\r" not in rendered and "\n" not in rendered
        for text in (rendered, formatted, caplog.text, str(record.args)):
            assert _PASSWORD_SENTINEL not in text
            assert _CA_SENTINEL not in text
            assert _CA_PEM not in text

    def test_ca_cert_is_passed_when_verification_enabled(self, mocker, caplog):
        from apps.opspilot.metis.llm.tools.activedirectory.connection import get_ad_connection_from_item

        tls, _server, connection, fake_conn = _patch_ldap(mocker)
        caplog.set_level(logging.DEBUG, logger="opspilot")

        result = get_ad_connection_from_item(_credential_item(_ad_config(verify_cert=True, ca_cert=f"\n{_CA_PEM}\n")))

        assert result is fake_conn
        tls.assert_called_once_with(validate=ssl.CERT_REQUIRED, version=ssl.PROTOCOL_TLS_CLIENT, ca_certs_data=_CA_PEM)
        assert connection.call_args.kwargs["password"] == _PASSWORD_SENTINEL
        assert not any(record.levelno >= logging.WARNING for record in caplog.records)
        assert _CA_SENTINEL not in caplog.text
        assert _PASSWORD_SENTINEL not in caplog.text

    def test_test_ad_instance_uses_same_tls_policy(self, mocker):
        from apps.opspilot.metis.llm.tools.activedirectory.connection import test_ad_instance

        tls, _server, _connection, _fake_conn = _patch_ldap(mocker)

        assert test_ad_instance(_ad_config()) is True
        tls.assert_called_once_with(validate=ssl.CERT_REQUIRED, version=ssl.PROTOCOL_TLS_CLIENT)

        tls.reset_mock()
        assert test_ad_instance(_ad_config(verify_cert=False, ca_cert=_CA_PEM)) is True
        tls.assert_called_once_with(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLS_CLIENT)

        tls.reset_mock()
        assert test_ad_instance(_ad_config(ca_cert=_CA_PEM)) is True
        tls.assert_called_once_with(validate=ssl.CERT_REQUIRED, version=ssl.PROTOCOL_TLS_CLIENT, ca_certs_data=_CA_PEM)


class _PagedLdap:
    def __init__(self, pages):
        self._pages = list(pages)
        self.calls = []
        self.entries = []
        self.result = {}
        self.last_error = ""

    def search(self, search_base, search_filter, search_scope, attributes, size_limit=0, paged_size=None, paged_cookie=None):
        _ = (search_base, search_filter, search_scope, attributes)
        self.calls.append({"size_limit": size_limit, "paged_size": paged_size, "paged_cookie": paged_cookie, "search_filter": search_filter})
        entries, cookie, code = self._pages.pop(0)
        self.entries = entries
        controls = {}
        if cookie is not None:
            controls["1.2.840.113556.1.4.319"] = {"value": {"cookie": cookie}}
        self.result = {"result": code, "description": "success" if code == 0 else "sizeLimitExceeded", "controls": controls}
        return code in {0, 4}


def _user(name):
    return FakeEntry(sAMAccountName=name, distinguishedName=f"CN={name}")


def _single_directory():
    config = _ad_config()
    return {
        "mode": "single",
        "legacy_single": True,
        "items": [{"index": 0, "name": "AD", "raw": config, "config": config}],
    }


class TestActiveDirectoryPaging:
    def test_one_query_reads_every_ldap_page(self, mocker):
        from apps.opspilot.metis.llm.tools.activedirectory import tools as ad_tools

        conn = _PagedLdap(
            [
                ([_user("alice"), _user("bob")], b"page-2", 0),
                ([_user("cara"), _user("drew")], b"page-3", 0),
                ([_user("erin")], None, 0),
            ]
        )
        mocker.patch.object(ad_tools, "AD_LDAP_PAGE_SIZE", 2)
        mocker.patch.object(ad_tools, "build_ad_normalized_from_runnable", return_value=_single_directory())
        mocker.patch.object(ad_tools, "get_ad_connection_from_item", return_value=conn)
        unbind = mocker.patch.object(ad_tools, "safe_unbind")

        result = ad_tools.activedirectory_run_query.func("SELECT SAMAccountName FROM User", config={})

        assert [call["paged_cookie"] for call in conn.calls] == [None, b"page-2", b"page-3"]
        assert [call["paged_size"] for call in conn.calls] == [2, 2, 2]
        assert all(call["size_limit"] == 0 for call in conn.calls)
        assert result.splitlines() == ["SAMAccountName", "alice", "bob", "cara", "drew", "erin"]
        assert "结果已截断" not in result
        unbind.assert_called_once_with(conn)

    def test_simple_limit_stops_without_asking_the_model_for_pages(self, mocker):
        from apps.opspilot.metis.llm.tools.activedirectory import tools as ad_tools

        conn = _PagedLdap(
            [
                ([_user("alice")], b"more", 0),
                ([_user("bob")], None, 0),
            ]
        )
        mocker.patch.object(ad_tools, "build_ad_normalized_from_runnable", return_value=_single_directory())
        mocker.patch.object(ad_tools, "get_ad_connection_from_item", return_value=conn)
        mocker.patch.object(ad_tools, "safe_unbind")

        result = ad_tools.activedirectory_run_query.func("SELECT SAMAccountName FROM User LIMIT 1", config={})

        assert len(conn.calls) == 1
        assert conn.calls[0]["paged_size"] == 1
        assert result.splitlines() == ["SAMAccountName", "alice"]
        assert "结果已截断" not in result

    def test_cap_appends_one_truncation_notice_and_logs_counts_only(self, mocker, caplog):
        from apps.opspilot.metis.llm.tools.activedirectory import sql_engine
        from apps.opspilot.metis.llm.tools.activedirectory import tools as ad_tools

        conn = _PagedLdap(
            [
                ([_user("alice"), _user("bob")], b"page-2", 0),
                ([_user("cara"), _user("drew")], b"page-3", 0),
                ([_user("erin"), _user("fran")], None, 0),
            ]
        )
        mocker.patch.object(sql_engine, "AD_LDAP_FETCH_CAP", 4)
        mocker.patch.object(ad_tools, "AD_LDAP_PAGE_SIZE", 2)
        mocker.patch.object(ad_tools, "build_ad_normalized_from_runnable", return_value=_single_directory())
        mocker.patch.object(ad_tools, "get_ad_connection_from_item", return_value=conn)
        mocker.patch.object(ad_tools, "safe_unbind")
        caplog.set_level(logging.DEBUG, logger="opspilot")

        result = ad_tools.activedirectory_run_query.func("SELECT SAMAccountName FROM User", config={})

        assert result.splitlines()[:5] == ["SAMAccountName", "alice", "bob", "cara", "drew"]
        assert result.endswith(
            "结果已截断：该域控的单次查询上限为 4 条，本次 LDAP 读取在 4 条停止，目录里还有更多对象。"
            "WHERE 只过滤已经读回的记录，LIMIT/OFFSET 也不能读到上限之外。计数只统计已读取的记录。"
            "这是配置上限，不是查询故障。如需更完整的结果，请提高该域控的单次查询上限。"
        )
        assert "erin" not in result
        warnings = [record for record in caplog.records if record.msg == ad_tools._AD_LDAP_TRUNCATED]
        assert len(warnings) == 1
        record = warnings[0]
        assert record.name == "opspilot"
        assert record.levelno == logging.WARNING
        assert record.args == (4, 4)
        assert record.exc_info is None
        rendered = record.getMessage()
        formatted = logging.Formatter("%(levelname)s %(name)s %(message)s").format(record)
        assert rendered == "event=ad_ldap_search_truncated fetched=4 fetch_cap=4"
        for text in (rendered, formatted, caplog.text, str(record.args), result):
            assert _PASSWORD_SENTINEL not in text
            assert _CA_SENTINEL not in text

    def test_server_size_limit_without_cookie_is_truncated(self):
        from apps.opspilot.metis.llm.tools.activedirectory.tools import _ldap_searcher

        conn = _PagedLdap([([_user("alice"), _user("bob")], None, 4)])

        found = _ldap_searcher(conn, "DC=example,DC=com", "(objectClass=user)", ["sAMAccountName"], 100)

        assert [entry.entry_attributes_as_dict["sAMAccountName"] for entry in found] == ["alice", "bob"]
        assert found.truncated is True

    def test_filtered_and_sorted_queries_fetch_until_the_cap(self):
        from apps.opspilot.metis.llm.tools.activedirectory.sql_engine import AD_LDAP_FETCH_CAP, execute_select

        requested = []

        def searcher(base_dn, search_filter, attrs, size_limit):
            _ = (base_dn, search_filter, attrs)
            requested.append(size_limit)
            return []

        execute_select("SELECT SAMAccountName FROM User", base_dn="DC=example,DC=com", searcher=searcher)
        execute_select("SELECT SAMAccountName FROM User LIMIT 10 OFFSET 5", base_dn="DC=example,DC=com", searcher=searcher)
        execute_select(
            "SELECT SAMAccountName FROM User WHERE Department = 'IT' LIMIT 10",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )
        execute_select(
            "SELECT SAMAccountName FROM User ORDER BY SAMAccountName LIMIT 10",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )
        execute_select(
            "SELECT u.SAMAccountName, g.CN FROM User u LEFT JOIN Group g ON u.DN = g.Member LIMIT 5",
            base_dn="DC=example,DC=com",
            searcher=searcher,
        )

        assert requested == [AD_LDAP_FETCH_CAP, 15, AD_LDAP_FETCH_CAP, AD_LDAP_FETCH_CAP, AD_LDAP_FETCH_CAP, AD_LDAP_FETCH_CAP]

    def test_configured_fetch_limit_stops_at_that_count(self, mocker):
        from apps.opspilot.metis.llm.tools.activedirectory import tools as ad_tools

        conn = _PagedLdap(
            [
                ([_user("alice")], b"page-2", 0),
                ([_user("bob")], b"page-3", 0),
                ([_user("cara")], None, 0),
            ]
        )
        directory = _single_directory()
        directory["items"][0]["config"]["fetch_limit"] = 2
        mocker.patch.object(ad_tools, "AD_LDAP_PAGE_SIZE", 1)
        mocker.patch.object(ad_tools, "build_ad_normalized_from_runnable", return_value=directory)
        mocker.patch.object(ad_tools, "get_ad_connection_from_item", return_value=conn)
        mocker.patch.object(ad_tools, "safe_unbind")

        result = ad_tools.activedirectory_run_query.func(
            "SELECT SAMAccountName FROM User",
            config={"configurable": {"ad_fetch_limit": "9"}},
        )

        assert len(conn.calls) == 2
        assert result.splitlines()[:3] == ["SAMAccountName", "alice", "bob"]
        assert "该域控的单次查询上限为 2 条" in result
        assert "本次 LDAP 读取在 2 条停止" in result
        assert "这是配置上限，不是查询故障" in result
        assert "cara" not in result


def test_resolve_ad_fetch_limit_defaults_and_clamps():
    from apps.opspilot.metis.llm.tools.activedirectory.sql_engine import AD_LDAP_FETCH_CAP, AD_LDAP_FETCH_CEILING, resolve_ad_fetch_limit

    assert resolve_ad_fetch_limit(None) == AD_LDAP_FETCH_CAP
    assert resolve_ad_fetch_limit("") == AD_LDAP_FETCH_CAP
    assert resolve_ad_fetch_limit("   ") == AD_LDAP_FETCH_CAP
    assert resolve_ad_fetch_limit("abc") == AD_LDAP_FETCH_CAP
    assert resolve_ad_fetch_limit(0) == AD_LDAP_FETCH_CAP
    assert resolve_ad_fetch_limit("-3") == AD_LDAP_FETCH_CAP
    assert resolve_ad_fetch_limit("20000") == 20000
    assert resolve_ad_fetch_limit(AD_LDAP_FETCH_CEILING + 1) == AD_LDAP_FETCH_CEILING


def test_normalize_keeps_each_domain_controller_fetch_limit():
    from apps.opspilot.metis.llm.tools.activedirectory.connection import normalize_ad_instance
    from apps.opspilot.metis.llm.tools.activedirectory.sql_engine import AD_LDAP_FETCH_CEILING

    assert normalize_ad_instance(_ad_config())["fetch_limit"] is None
    assert normalize_ad_instance(_ad_config(fetch_limit="25000"))["fetch_limit"] == 25000
    assert normalize_ad_instance(_ad_config(fetch_limit="nope"))["fetch_limit"] is None
    assert normalize_ad_instance(_ad_config(fetch_limit=AD_LDAP_FETCH_CEILING + 5))["fetch_limit"] == AD_LDAP_FETCH_CEILING


def test_execute_select_uses_configured_fetch_cap():
    from apps.opspilot.metis.llm.tools.activedirectory.sql_engine import execute_select

    requested = []

    def searcher(base_dn, search_filter, attrs, size_limit):
        _ = (base_dn, search_filter, attrs)
        requested.append(size_limit)
        return []

    execute_select("SELECT SAMAccountName FROM User", base_dn="DC=example,DC=com", searcher=searcher, fetch_cap=30)
    execute_select(
        "SELECT SAMAccountName FROM User LIMIT 10 OFFSET 5",
        base_dn="DC=example,DC=com",
        searcher=searcher,
        fetch_cap=30,
    )
    execute_select(
        "SELECT SAMAccountName FROM User WHERE Department = 'IT' LIMIT 10",
        base_dn="DC=example,DC=com",
        searcher=searcher,
        fetch_cap=30,
    )

    assert requested == [30, 15, 30]


def test_negative_builtin_ad_fetch_limit_reaches_runtime_config(mocker):
    from apps.opspilot.services.builtin_tools import BUILTIN_ACTIVEDIRECTORY_TOOL_ID, BUILTIN_ACTIVEDIRECTORY_TOOL_NAME
    from apps.opspilot.services.chat_service import ChatService

    llm_model = mocker.Mock()
    llm_model.openai_api_base = "https://example.com/v1"
    llm_model.openai_api_key = "key"
    llm_model.model_name = "gpt-4o"
    llm_model.protocol_type = "openai"
    llm_model.vendor_id = None
    llm_model.pk = 1
    llm_model.context_window_tokens = 128000
    mocker.patch("apps.opspilot.services.history_service.history_service.process_user_message_and_images", return_value=("hello", []))
    mocker.patch("apps.opspilot.services.history_service.history_service.process_chat_history", return_value=[])
    mocker.patch("apps.opspilot.services.chat_service.resolve_skill_params", return_value="system")
    mocker.patch("apps.opspilot.services.chat_service.SkillTools.objects.filter", return_value=[])
    instances = '[{"id":"ad-1","name":"AD - 1","host":"dc.example.com","bind_password":"secret-value"}]'
    request = {
        "user_message": "hello",
        "chat_history": [],
        "skill_prompt": "system",
        "skill_params": [],
        "temperature": 0.1,
        "user_id": 1,
        "enable_rag": False,
        "enable_rag_knowledge_source": False,
        "skill_type": 1,
        "locale": "zh-Hans",
        "tools": [
            {
                "id": BUILTIN_ACTIVEDIRECTORY_TOOL_ID,
                "name": BUILTIN_ACTIVEDIRECTORY_TOOL_NAME,
                "kwargs": [
                    {"key": "ad_instances", "value": instances, "type": "string"},
                    {"key": "ad_default_instance_id", "value": "ad-1", "type": "string"},
                    {"key": "ad_fetch_limit", "value": "20000", "type": "string"},
                ],
            }
        ],
    }

    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(request, llm_model)

    extra = chat_kwargs["extra_config"]
    assert extra["ad_instances"] == instances
    assert extra["ad_default_instance_id"] == "ad-1"
    assert extra["ad_fetch_limit"] == "20000"

    request["tools"][0]["kwargs"] = [item for item in request["tools"][0]["kwargs"] if item["key"] != "ad_fetch_limit"]
    blank_kwargs, _, _ = ChatService.format_chat_server_kwargs(request, llm_model)
    assert "ad_fetch_limit" not in blank_kwargs["extra_config"]
    assert blank_kwargs["extra_config"]["ad_instances"] == instances
