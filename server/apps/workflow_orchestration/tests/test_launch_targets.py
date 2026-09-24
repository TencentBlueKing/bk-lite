import pytest

from apps.workflow_orchestration.services.launch_plans import LaunchPlanTokenError, build_launch_plan, extract_target_fields, verify_launch_token
from apps.workflow_orchestration.services.target_resolver import TargetResolutionError, resolve_target_fields


class FakeTargetGateway:
    def resolve(self, source, source_ids):
        records = {
            "node_mgmt": {
                "linux-1": {
                    "id": "node:linux-1",
                    "source": "node_mgmt",
                    "source_id": "linux-1",
                    "name": "linux-1",
                    "ip": "10.0.0.1",
                    "operating_system": "linux",
                    "cloud_region_id": 1,
                    "connected": True,
                },
                "linux-offline": {
                    "id": "node:linux-offline",
                    "source": "node_mgmt",
                    "source_id": "linux-offline",
                    "name": "linux-offline",
                    "ip": "10.0.0.2",
                    "operating_system": "linux",
                    "cloud_region_id": 1,
                    "connected": False,
                },
                "aix-1": {
                    "id": "node:aix-1",
                    "source": "node_mgmt",
                    "source_id": "aix-1",
                    "name": "aix-1",
                    "ip": "10.0.0.3",
                    "operating_system": "aix",
                    "cloud_region_id": 1,
                    "connected": True,
                },
            },
            "job_mgmt": {
                "11": {
                    "id": "manual:11",
                    "source": "job_mgmt",
                    "source_id": "11",
                    "name": "windows-1",
                    "ip": "10.0.0.11",
                    "operating_system": "windows",
                    "cloud_region_id": 1,
                    "connected": None,
                },
                "12": {
                    "id": "manual:12",
                    "source": "job_mgmt",
                    "source_id": "12",
                    "name": "ambiguous-linux",
                    "ip": "10.0.0.1",
                    "operating_system": "linux",
                    "cloud_region_id": 1,
                    "connected": None,
                },
            },
        }
        return [records[source][source_id] for source_id in source_ids if source_id in records[source]]


TARGET_FIELDS = [
    {
        "key": "targets",
        "required": True,
        "binding_mode": "runtime",
        "allowed_sources": ["node_mgmt", "job_mgmt"],
        "min_count": 1,
        "max_count": 100,
    }
]


def test_target_field_is_derived_from_generic_form_schema_extension():
    metadata = {
        "data_contract": {
            "inputs": [
                {
                    "key": "targets",
                    "name": "目标主机",
                    "required": True,
                    "sensitive": False,
                    "schema": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 20,
                        "x-widget": "target-selector",
                        "x-target-binding": {
                            "mode": "runtime",
                            "allowedSources": ["node_mgmt", "job_mgmt"],
                            "allowedOperatingSystems": ["linux", "windows"],
                            "minCount": 1,
                            "maxCount": 20,
                        },
                    },
                }
            ]
        }
    }

    assert extract_target_fields(metadata) == [
        {
            "key": "targets",
            "name": "目标主机",
            "required": True,
            "binding_mode": "runtime",
            "allowed_sources": ["node_mgmt", "job_mgmt"],
            "allowed_operating_systems": ["linux", "windows"],
            "min_count": 1,
            "max_count": 20,
        }
    ]


def test_launch_plan_token_is_bound_to_actor_team_workflow_and_version(settings):
    settings.SECRET_KEY = "launch-plan-secret"
    plan = build_launch_plan(
        workflow_id=7,
        workflow_name="巡检",
        workflow_version=3,
        canvas_metadata={"input_schema": {"type": "object", "properties": {}}},
        team=9,
        username="alice",
        domain="example.com",
        target_fields=TARGET_FIELDS,
    )

    payload = verify_launch_token(
        plan["launch_token"],
        workflow_id=7,
        team=9,
        username="alice",
        domain="example.com",
    )

    assert plan["workflow_version"] == 3
    assert plan["target_fields"] == TARGET_FIELDS
    assert payload["workflow_version"] == 3
    with pytest.raises(LaunchPlanTokenError, match="操作者"):
        verify_launch_token(
            plan["launch_token"],
            workflow_id=7,
            team=9,
            username="bob",
            domain="example.com",
        )


def test_resolve_multiple_target_fields_uses_global_unique_limit_and_keeps_snapshots():
    fields = [
        TARGET_FIELDS[0],
        {**TARGET_FIELDS[0], "key": "secondary", "max_count": 2},
    ]

    result = resolve_target_fields(
        {
            "targets": ["node:linux-1", "manual:11"],
            "secondary": ["node:linux-1", "node:linux-offline"],
        },
        fields,
        gateway=FakeTargetGateway(),
        total_limit=3,
    )

    assert result.unique_total == 3
    assert result.inputs["targets"][0]["id"] == "node:linux-1"
    assert result.snapshot["fields"]["secondary"]["offline_count"] == 1
    assert result.offline_targets[0]["id"] == "node:linux-offline"


def test_resolve_targets_blocks_missing_and_cross_source_identity_conflict():
    with pytest.raises(TargetResolutionError, match="不存在或无权"):
        resolve_target_fields(
            {"targets": ["node:missing"]},
            TARGET_FIELDS,
            gateway=FakeTargetGateway(),
        )

    with pytest.raises(TargetResolutionError, match="身份冲突"):
        resolve_target_fields(
            {"targets": ["node:linux-1", "manual:12"]},
            TARGET_FIELDS,
            gateway=FakeTargetGateway(),
        )


def test_resolve_targets_blocks_total_limit_instead_of_partially_continuing():
    with pytest.raises(TargetResolutionError, match="总数不能超过 1"):
        resolve_target_fields(
            {"targets": ["node:linux-1", "manual:11"]},
            TARGET_FIELDS,
            gateway=FakeTargetGateway(),
            total_limit=1,
        )


def test_resolve_targets_rejects_unsupported_operating_system_before_execution():
    fields = [{**TARGET_FIELDS[0], "allowed_operating_systems": ["linux", "windows"]}]

    with pytest.raises(TargetResolutionError, match="AIX|aix"):
        resolve_target_fields(
            {"targets": ["node:aix-1"]},
            fields,
            gateway=FakeTargetGateway(),
        )
