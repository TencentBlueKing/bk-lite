# -*- coding: utf-8 -*-
"""Oracle 采集拓扑识别：有无 CDB/PDB/RAC 都走同一套落盘键。"""

from __future__ import annotations

from typing import Any, Iterable

CDB_ROOT = "CDB$ROOT"
SEED_PDB = "PDB$SEED"
SCOPE_CDB = "cdb"
SCOPE_PDB = "pdb"
SCOPE_NON_CDB = "non_cdb"
CLUSTER_RAC = "rac"
CLUSTER_STANDALONE = "standalone"


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def classify_collect_scope(*, con_name: str = "", is_cdb: bool | None = None, pdbs_available: bool = False) -> str:
    name = _upper(con_name)
    if is_cdb is False:
        return SCOPE_NON_CDB
    if name == CDB_ROOT:
        return SCOPE_CDB
    if name and name != CDB_ROOT:
        return SCOPE_PDB
    if is_cdb is True or pdbs_available:
        return SCOPE_CDB
    return SCOPE_NON_CDB


def parse_cdb_flag(value: Any) -> bool | None:
    text = _upper(value)
    if text in {"YES", "TRUE", "Y", "1"}:
        return True
    if text in {"NO", "FALSE", "N", "0"}:
        return False
    return None


def database_inst_name(db_unique_name: str = "", db_name: str = "") -> str:
    return str(db_unique_name or db_name or "").strip()


def instance_inst_name(db_key: str, sid: str) -> str:
    db_key = str(db_key or "").strip()
    sid = str(sid or "").strip()
    if db_key and sid:
        return f"{db_key}-{sid}"
    return sid or db_key


def pdb_inst_name(db_key: str, pdb_name: str) -> str:
    db_key = str(db_key or "").strip()
    pdb_name = str(pdb_name or "").strip()
    if db_key and pdb_name:
        return f"{db_key}-{pdb_name}"
    return pdb_name


def cluster_type(instance_count: int) -> str:
    return CLUSTER_RAC if instance_count > 1 else CLUSTER_STANDALONE


def filter_business_pdbs(pdbs: Iterable[dict], *, scope: str, current_pdb: str = "") -> list[dict]:
    if scope == SCOPE_NON_CDB:
        return []
    current = _upper(current_pdb)
    result = []
    for pdb in pdbs:
        name = str(pdb.get("name") or pdb.get("NAME") or "").strip()
        if not name or _upper(name) == SEED_PDB:
            continue
        if scope == SCOPE_PDB and current and _upper(name) != current:
            continue
        result.append(pdb)
    return result


def build_dsn_parts(*, host: str, port: int, service_name: str = "", sid: str = "") -> dict[str, Any]:
    service_name = str(service_name or "").strip()
    sid = str(sid or "").strip()
    if service_name:
        return {"host": host, "port": int(port), "service_name": service_name}
    if sid:
        return {"host": host, "port": int(port), "sid": sid}
    raise ValueError("service_name or sid is required")
