import pytest
from plugins.inputs.oracle.oracle_info import OracleInfo
from tests.test_db_plugins_native_async import _OracleConn


@pytest.mark.asyncio
async def test_oracle_cdb_collects_instances_and_pdbs(monkeypatch):
    rows = {
        OracleInfo.SQL_QUERIES["con_name"]: {"CON_NAME": "CDB$ROOT"},
        OracleInfo.SQL_QUERIES["database"]: {
            "NAME": "ORCL",
            "DB_UNIQUE_NAME": "orcl_unique",
            "DATABASE_ROLE": "PRIMARY",
            "LOG_MODE": "ARCHIVELOG",
            "OPEN_MODE": "READ WRITE",
        },
        OracleInfo.SQL_QUERIES["cdb_flag"]: {"CDB": "YES"},
        OracleInfo.SQL_QUERIES["version"]: {"BANNER": "Oracle Database 19c"},
        OracleInfo.SQL_QUERIES["sga_max_size"]: {"VALUE": "2048"},
        OracleInfo.SQL_QUERIES["max_conn"]: {"VALUE": 400},
        OracleInfo.SQL_QUERIES["instance"]: {
            "SID": "ORCL1",
            "HOST_NAME": "db-1",
            "STATUS": "OPEN",
            "VERSION": "19.0.0.0.0",
        },
        OracleInfo.SQL_QUERIES["gv_instance"]: [
            {"SID": "ORCL1", "HOST_NAME": "db-1", "STATUS": "OPEN", "VERSION": "19.0.0.0.0", "INSTANCE_NUMBER": 1},
            {"SID": "ORCL2", "HOST_NAME": "db-2", "STATUS": "OPEN", "VERSION": "19.0.0.0.0", "INSTANCE_NUMBER": 2},
        ],
        OracleInfo.SQL_QUERIES["pdbs"]: [
            {"NAME": "PDB$SEED", "OPEN_MODE": "READ ONLY", "RESTRICTED": "NO"},
            {"NAME": "ORCLPDB1", "OPEN_MODE": "READ WRITE", "RESTRICTED": "NO"},
        ],
    }

    async def connect_async(**_kwargs):
        return _OracleConn(rows)

    monkeypatch.setattr("plugins.inputs.oracle.oracle_info.oracledb.connect_async", connect_async)
    result = await OracleInfo({"host": "10.0.0.10", "port": 1521, "user": "c##cmdb", "password": "x", "service_name": "orcl"}).list_all_resources()
    assert result["success"] is True
    oracle = result["result"]["oracle"][0]
    assert oracle["collect_scope"] == "cdb"
    assert oracle["cluster_type"] == "rac"
    assert oracle["instance_count"] == "2"
    assert oracle["pdb_count"] == "1"
    assert {item["sid"] for item in result["result"]["oracle_instance"]} == {"ORCL1", "ORCL2"}
    assert result["result"]["oracle_pdb"][0]["pdb_name"] == "ORCLPDB1"


@pytest.mark.asyncio
async def test_oracle_pdb_scope_only_upserts_current_pdb(monkeypatch):
    rows = {
        OracleInfo.SQL_QUERIES["con_name"]: {"CON_NAME": "ORCLPDB1"},
        OracleInfo.SQL_QUERIES["database"]: {
            "NAME": "ORCL",
            "DB_UNIQUE_NAME": "orcl_unique",
            "DATABASE_ROLE": "PRIMARY",
            "LOG_MODE": "ARCHIVELOG",
            "OPEN_MODE": "READ WRITE",
        },
        OracleInfo.SQL_QUERIES["cdb_flag"]: {"CDB": "YES"},
        OracleInfo.SQL_QUERIES["version"]: {"BANNER": "Oracle Database 19c"},
        OracleInfo.SQL_QUERIES["instance"]: {
            "SID": "ORCL1",
            "HOST_NAME": "db-1",
            "STATUS": "OPEN",
            "VERSION": "19.0.0.0.0",
        },
        OracleInfo.SQL_QUERIES["pdbs"]: [
            {"NAME": "ORCLPDB1", "OPEN_MODE": "READ WRITE", "RESTRICTED": "NO"},
            {"NAME": "ORCLPDB2", "OPEN_MODE": "READ WRITE", "RESTRICTED": "NO"},
        ],
    }

    async def connect_async(**_kwargs):
        return _OracleConn(rows)

    monkeypatch.setattr("plugins.inputs.oracle.oracle_info.oracledb.connect_async", connect_async)
    result = await OracleInfo({"host": "10.0.0.10", "port": 1521, "user": "app", "password": "x", "sid": "ORCL1"}).list_all_resources()
    assert result["success"] is True
    assert result["result"]["oracle"][0]["collect_scope"] == "pdb"
    assert [item["pdb_name"] for item in result["result"]["oracle_pdb"]] == ["ORCLPDB1"]


@pytest.mark.asyncio
async def test_oracle_connect_requires_sid_or_service():
    result = await OracleInfo({"host": "10.0.0.10", "port": 1521, "user": "app", "password": "x"}).list_all_resources()
    assert result["success"] is False
    assert "service_name or sid" in result["result"]["cmdb_collect_error"]
