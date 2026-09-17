from plugins.inputs.oracle.oracle_topology import (
    build_dsn_parts,
    classify_collect_scope,
    cluster_type,
    database_inst_name,
    filter_business_pdbs,
    instance_inst_name,
    parse_cdb_flag,
    pdb_inst_name,
)


def test_classify_non_cdb_when_cdb_flag_no():
    assert classify_collect_scope(con_name="ORCL", is_cdb=False, pdbs_available=False) == "non_cdb"


def test_classify_cdb_root():
    assert classify_collect_scope(con_name="CDB$ROOT", is_cdb=True, pdbs_available=True) == "cdb"


def test_classify_pdb_container():
    assert classify_collect_scope(con_name="ORCLPDB1", is_cdb=True, pdbs_available=True) == "pdb"


def test_classify_missing_views_is_non_cdb():
    assert classify_collect_scope(con_name="", is_cdb=None, pdbs_available=False) == "non_cdb"


def test_identity_and_cluster_type():
    assert database_inst_name("orcl_unique", "ORCL") == "orcl_unique"
    assert database_inst_name("", "ORCL") == "ORCL"
    assert instance_inst_name("orcl_unique", "ORCL1") == "orcl_unique-ORCL1"
    assert pdb_inst_name("orcl_unique", "ORCLPDB1") == "orcl_unique-ORCLPDB1"
    assert cluster_type(1) == "standalone"
    assert cluster_type(2) == "rac"


def test_filter_pdbs_skips_seed_and_siblings_in_pdb_scope():
    pdbs = [{"name": "PDB$SEED"}, {"name": "ORCLPDB1"}, {"name": "ORCLPDB2"}]
    assert [p["name"] for p in filter_business_pdbs(pdbs, scope="cdb")] == ["ORCLPDB1", "ORCLPDB2"]
    assert [p["name"] for p in filter_business_pdbs(pdbs, scope="pdb", current_pdb="ORCLPDB1")] == ["ORCLPDB1"]
    assert filter_business_pdbs(pdbs, scope="non_cdb") == []


def test_build_dsn_prefers_service_name_then_sid():
    assert build_dsn_parts(host="10.0.0.1", port=1521, service_name="orcl")["service_name"] == "orcl"
    assert build_dsn_parts(host="10.0.0.1", port=1521, sid="ORCL")["sid"] == "ORCL"


def test_build_dsn_requires_one_connect_target():
    try:
        build_dsn_parts(host="10.0.0.1", port=1521)
    except ValueError as exc:
        assert "service_name or sid" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_parse_cdb_flag():
    assert parse_cdb_flag("YES") is True
    assert parse_cdb_flag("NO") is False
    assert parse_cdb_flag("") is None
