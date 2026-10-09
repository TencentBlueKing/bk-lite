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
