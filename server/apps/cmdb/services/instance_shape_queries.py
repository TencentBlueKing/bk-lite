"""实例形态修复的图查询语句。只返回节点 id 和需要判断的字段。"""

from __future__ import annotations

import os

from apps.cmdb.graph.validators import CQLValidator

_LIST_TYPEOF = "['List', 'list', 'array', 'Array']"
_PAGE_SIZE = 500


def graph_driver_name() -> str:
    if os.getenv("FALKORDB_HOST", ""):
        return "falkordb"
    return "neo4j"


def organization_repair_statement(*, driver: str, after_id: int | None, limit: int = _PAGE_SIZE) -> tuple[str, dict]:
    params: dict = {"limit": int(limit)}
    after_clause = ""
    if after_id is not None:
        params["after_id"] = int(after_id)
        after_clause = "AND ID(n) > $after_id"
    if driver == "falkordb":
        predicate = (
            "("
            "n.organization IS NULL "
            "OR n.organization = '' "
            "OR typeof(n.organization) = 'integer' "
            "OR typeof(n.organization) = 'Integer' "
            f"OR (typeof(n.organization) IN {_LIST_TYPEOF} AND size(n.organization) = 0)"
            ")"
        )
    else:
        predicate = (
            "("
            "n.organization IS NULL "
            "OR n.organization = '' "
            "OR n.organization IS :: INTEGER "
            "OR (n.organization IS :: LIST AND size(n.organization) = 0)"
            ")"
        )
    statement = (
        "MATCH (n:INSTANCE) "
        f"WHERE {predicate} {after_clause} "
        "RETURN ID(n) AS id, n.organization AS organization "
        "ORDER BY ID(n) "
        "LIMIT $limit"
    )
    return statement, params


def scalar_repair_statement(
    *,
    driver: str,
    model_id: str,
    fields: list[str],
    after_id: int | None,
    limit: int = _PAGE_SIZE,
) -> tuple[str, dict]:
    validated_fields = [CQLValidator.validate_field(field) for field in fields]
    if not validated_fields:
        raise ValueError("scalar repair requires at least one field")
    params: dict = {"limit": int(limit), "model_id": model_id}
    after_clause = ""
    if after_id is not None:
        params["after_id"] = int(after_id)
        after_clause = "AND ID(n) > $after_id"
    predicates = []
    returns = ["ID(n) AS id"]
    for field in validated_fields:
        if driver == "falkordb":
            predicates.append(f"(n.{field} IS NOT NULL AND NOT typeof(n.{field}) IN {_LIST_TYPEOF})")
        else:
            predicates.append(f"(n.{field} IS NOT NULL AND NOT n.{field} IS :: LIST)")
        returns.append(f"n.{field} AS {field}")
    statement = (
        "MATCH (n:INSTANCE) "
        f"WHERE n.model_id = $model_id AND ({' OR '.join(predicates)}) {after_clause} "
        f"RETURN {', '.join(returns)} "
        "ORDER BY ID(n) "
        "LIMIT $limit"
    )
    return statement, params
