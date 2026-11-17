import pytest

from apps.cmdb.services.instance_shape_queries import organization_repair_statement, scalar_repair_statement


def test_falkordb_organization_statement_uses_typeof_and_keeps_strings_for_scalar_stage():
    statement, params = organization_repair_statement(driver="falkordb", after_id=15, limit=500)

    assert "typeof(n.organization) = 'integer'" in statement
    assert "typeof(n.organization) = 'Integer'" in statement
    assert "size(n.organization) = 0" in statement
    assert "IS ::" not in statement
    assert params == {"limit": 500, "after_id": 15}


def test_neo4j_organization_statement_uses_type_predicates():
    statement, params = organization_repair_statement(driver="neo4j", after_id=None, limit=500)

    assert "n.organization IS :: INTEGER" in statement
    assert "n.organization IS :: LIST" in statement
    assert "typeof(" not in statement
    assert "after_id" not in params


def test_scalar_statement_selects_non_list_values_for_one_model():
    statement, params = scalar_repair_statement(
        driver="neo4j",
        model_id="host",
        fields=["organization", "status"],
        after_id=4,
        limit=500,
    )

    assert "n.model_id = $model_id" in statement
    assert "NOT n.organization IS :: LIST" in statement
    assert "NOT n.status IS :: LIST" in statement
    assert "n.organization AS organization" in statement
    assert params["model_id"] == "host"
    assert params["after_id"] == 4


def test_scalar_statement_rejects_empty_field_list():
    with pytest.raises(ValueError):
        scalar_repair_statement(driver="falkordb", model_id="host", fields=[], after_id=None)
