import json

import pytest
from rest_framework.exceptions import ValidationError

from apps.cmdb.open_api.serializers import (
    InstanceListQuerySerializer,
    validate_instance_payload,
)


ATTRS = [
    {"attr_id": "inst_name", "attr_type": "str", "editable": True},
    {"attr_id": "ip_addr", "attr_type": "str", "editable": True},
    {"attr_id": "serial", "attr_type": "str", "editable": False},
    {"attr_id": "organization", "attr_type": "organization", "editable": True},
]


def test_query_parses_filters_and_maps_public_order_field():
    serializer = InstanceListQuerySerializer(
        data={
            "page": "2",
            "page_size": "50",
            "order": "-updated_at",
            "filters": '[{"field":"ip_addr","type":"str*","value":"10."}]',
        },
        context={"attrs": ATTRS},
    )
    serializer.is_valid(raise_exception=True)
    assert serializer.validated_data["order"] == "-_updated_at"
    assert serializer.validated_data["filters"][0]["field"] == "ip_addr"


@pytest.mark.parametrize("field", ["organization", "_creator", "unknown"])
def test_query_rejects_unsafe_or_unknown_filter_field(field):
    serializer = InstanceListQuerySerializer(
        data={"filters": json.dumps([{"field": field, "type": "str=", "value": "x"}])},
        context={"attrs": ATTRS},
    )
    assert not serializer.is_valid()


def test_query_rejects_operator_incompatible_with_attribute_type():
    serializer = InstanceListQuerySerializer(
        data={"filters": json.dumps([{"field": "ip_addr", "type": "int=", "value": 10}])},
        context={"attrs": ATTRS},
    )
    assert not serializer.is_valid()


def test_create_payload_forces_team_and_rejects_system_fields():
    assert validate_instance_payload({"inst_name": "h1"}, ATTRS, team_id=7, for_update=False)["organization"] == [7]
    with pytest.raises(ValidationError):
        validate_instance_payload({"_id": 1}, ATTRS, team_id=7, for_update=False)


def test_update_payload_rejects_organization_change():
    with pytest.raises(ValidationError):
        validate_instance_payload({"organization": [9]}, ATTRS, team_id=7, for_update=True)


def test_update_payload_rejects_readonly_attribute():
    with pytest.raises(ValidationError):
        validate_instance_payload({"serial": "changed"}, ATTRS, team_id=7, for_update=True)
