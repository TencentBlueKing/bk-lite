import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.collection.collect_tasks.base import BaseCollect
from apps.cmdb.constants.constants import CollectInputMethod
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.collect_task_credential_hit import CollectTaskCredentialHit
from apps.cmdb.models.scan_model import ScanExecution, ScanFamilyRun, ScanHit, ScanTask
from apps.cmdb.services.collect_service import CollectModelService
from apps.cmdb.services.scan_collect_generate import ScanCollectGenerateService, _normalize_credential_item

pytestmark = pytest.mark.django_db

HOST_UUIDS = {
    "10.0.1.10": "11111111-1111-4111-8111-111111111111",
    "10.0.1.12": "22222222-2222-4222-8222-222222222222",
    "10.0.1.11": "33333333-3333-4333-8333-333333333333",
    "10.0.1.20": "44444444-4444-4444-8444-444444444444",
}
INFLUX_UUIDS = {
    "10.0.1.60": "55555555-5555-4555-8555-555555555555",
    "10.0.1.61": "66666666-6666-4666-8666-666666666666",
}
HOST_FAMILY_UUIDS = {
    "10.0.1.70": "77777777-7777-4777-8777-777777777777",
}
ALL_UUIDS = {**HOST_UUIDS, **INFLUX_UUIDS, **HOST_FAMILY_UUIDS}


def _task(**overrides):
    values = {
        "name": "scan-gen",
        "team": [1],
        "families": ["network"],
        "access_point": [{"id": "node-1"}],
        "ip_ranges": [{"begin": "10.0.1.1", "end": "10.0.1.20"}],
        "credentials": {
            "network": [
                {
                    "credential_id": "cred-snmp-1",
                    "version": "v2",
                    "community": "public",
                    "snmp_port": "161",
                    "level": "authNoPriv",
                    "integrity": "sha",
                    "privacy": "aes",
                }
            ]
        },
    }
    values.update(overrides)
    return ScanTask.objects.create(**values)


def _execution_with_hits(
    task,
    hosts,
    *,
    family="network",
    driver_type="protocol",
    protocol="network",
    port=161,
    credential_id="cred-snmp-1",
    cmdb_model_id="switch",
    uuids=None,
):
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_COMPLETED)
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id=family,
        driver_type=driver_type,
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    uuid_map = uuids or HOST_UUIDS
    hits = []
    for host in hosts:
        hits.append(
            ScanHit.objects.create(
                execution=execution,
                family_run=family_run,
                protocol=protocol,
                host=host,
                port=port,
                credential_id=credential_id,
                status=ScanHit.STATUS_SUCCESS,
                cmdb_model_id=cmdb_model_id,
                inst_uuid=uuid_map[host],
                snapshot={"host": host, "brand": "Cisco"},
            )
        )
    return execution, hits


def _graph_row(inst_uuid):
    host = next(ip for ip, uuid in ALL_UUIDS.items() if uuid == inst_uuid)
    if inst_uuid in INFLUX_UUIDS.values():
        model_id = "influxdb"
        inst_name = f"{host}-influxdb-8086"
        extra = {"port": 8086}
    elif inst_uuid in HOST_FAMILY_UUIDS.values():
        model_id = "host"
        inst_name = host
        extra = {}
    else:
        model_id = "switch"
        inst_name = f"{host}-switch"
        extra = {"brand": "Cisco"}
    return {
        "inst_uuid": inst_uuid,
        "model_id": model_id,
        "ip_addr": host,
        "inst_name": inst_name,
        "organization": [1],
        **extra,
    }


def _request(user):
    factory = APIRequestFactory()
    request = factory.post("/x/", {}, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _patch_side_effects(mocker):
    mocker.patch("apps.cmdb.services.collect_service.transaction.on_commit", side_effect=lambda fn: fn())
    mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.create_or_update_periodic_task")
    mocker.patch("apps.cmdb.services.collect_service.create_change_record")
    mocker.patch.object(CollectModelService, "schedule_first_collection_if_needed", return_value=False)
    mocker.patch.object(CollectModelService, "schedule_delayed_sync_if_needed")
    mocker.patch.object(CollectModelService, "has_permission")
    mocker.patch(
        "apps.cmdb.serializers.collect_serializer.CollectModelSerializer._query_authorized_instances",
        side_effect=lambda inst_uuids: [_graph_row(item) for item in inst_uuids],
    )
    mocker.patch("apps.cmdb.permissions.inst_task_permission.get_cmdb_rules", return_value={})
    mocker.patch(
        "apps.cmdb.services.scan_collect_task.InstanceManage.query_entity_by_uuids",
        side_effect=lambda uuids: [{"_id": index + 1, **_graph_row(item)} for index, item in enumerate(uuids)],
    )
    fake_graph = mocker.MagicMock()
    fake_graph.set_entity_properties.return_value = []
    mocker.patch(
        "apps.cmdb.services.scan_collect_task.GraphClient",
        return_value=mocker.MagicMock(__enter__=mocker.Mock(return_value=fake_graph), __exit__=mocker.Mock(return_value=False)),
    )
    return fake_graph


def test_normalize_v2_credential_drops_v3_fields():
    normalized = _normalize_credential_item(
        "network",
        {
            "credential_id": "cred-snmp-1",
            "version": "v2",
            "community": "public",
            "snmp_port": "161",
            "level": "authNoPriv",
            "integrity": "sha",
            "privacy": "aes",
        },
    )
    assert normalized == {
        "credential_id": "cred-snmp-1",
        "version": "v2",
        "community": "public",
        "snmp_port": "161",
    }


def test_one_credential_multiple_ips_creates_single_collect_task(mocker, authenticated_user):
    fake_graph = _patch_side_effects(mocker)
    push = mocker.patch.object(CollectModelService, "push_butch_node_params")
    delete = mocker.patch.object(CollectModelService, "delete_butch_node_params")
    create = mocker.spy(CollectModelService, "create")
    task = _task()
    execution, hits = _execution_with_hits(task, ["10.0.1.10", "10.0.1.12"])

    result = ScanCollectGenerateService.generate(
        execution,
        [hit.id for hit in hits],
        operator="alice",
        request=_request(authenticated_user),
    )

    assert result["created"] == 1
    assert result["appended"] == 1
    assert create.call_count == 1
    collect = CollectModels.objects.get()
    assert collect.input_method == CollectInputMethod.AUTO
    assert collect.is_interval is True
    assert collect.cycle_value_type == "cycle"
    assert collect.cycle_value == "30"
    assert collect.timeout == 5
    assert collect.model_id == "network"
    assert collect.task_type == "snmp"
    assert collect.driver_type == "protocol"
    assert collect.ip_range in ("", None)
    instance_uuids = {item.get("inst_uuid") for item in (collect.instances or [])}
    assert instance_uuids == {HOST_UUIDS["10.0.1.10"], HOST_UUIDS["10.0.1.12"]}
    creds = collect.decrypt_credentials
    assert len(creds) == 1
    assert creds[0]["credential_id"] == "cred-snmp-1"
    assert creds[0]["community"] == "public"
    assert "level" not in creds[0]
    assert "integrity" not in creds[0]
    assert "privacy" not in creds[0]
    assert collect.params["has_network_topo"] is True
    assert collect.params["topology_protocols"] == ["lldp", "huawei_ndp", "cdp", "fdb", "arp"]
    assert collect.params["topology_fallback_strategy"] == "prefer_neighbors_then_fdb_then_arp"
    assert collect.params["min_confidence"] == 0.0
    runner = BaseCollect(instance_id=None, task=collect)
    assert runner.model_id == "network"
    fake_graph.set_entity_properties.assert_called_once()
    claim_args, claim_kwargs = fake_graph.set_entity_properties.call_args
    assert claim_args[2] == {"collect_task": str(collect.id)}
    assert claim_kwargs.get("check") is False
    assert push.call_count == 1
    assert delete.call_count == 0


def test_generate_uses_scan_range_that_contains_hits(mocker, authenticated_user):
    _patch_side_effects(mocker)
    mocker.patch.object(CollectModelService, "push_butch_node_params")
    mocker.patch.object(CollectModelService, "delete_butch_node_params")
    task = _task(
        ip_ranges=[
            {"begin": "10.0.2.1", "end": "10.0.2.10"},
            {"begin": "10.0.1.1", "end": "10.0.1.20"},
        ]
    )
    execution, hits = _execution_with_hits(task, ["10.0.1.10", "10.0.1.12"])

    ScanCollectGenerateService.generate(
        execution,
        [hit.id for hit in hits],
        operator="alice",
        request=_request(authenticated_user),
    )

    collect = CollectModels.objects.get()
    assert collect.ip_range in ("", None)
    instance_uuids = {item.get("inst_uuid") for item in (collect.instances or [])}
    assert instance_uuids == {HOST_UUIDS["10.0.1.10"], HOST_UUIDS["10.0.1.12"]}


def test_second_generate_appends_to_scan_created_task(mocker, authenticated_user):
    _patch_side_effects(mocker)
    push = mocker.patch.object(CollectModelService, "push_butch_node_params")
    delete = mocker.patch.object(CollectModelService, "delete_butch_node_params")
    task = _task()
    execution, hits = _execution_with_hits(task, ["10.0.1.10", "10.0.1.12"])
    request = _request(authenticated_user)

    first = ScanCollectGenerateService.generate(execution, [hits[0].id], operator="alice", request=request)
    assert first["created"] == 1
    second = ScanCollectGenerateService.generate(execution, [hits[1].id], operator="alice", request=request)

    assert second["appended"] == 1
    assert second["created"] == 0
    collect = CollectModels.objects.get()
    instance_uuids = {item.get("inst_uuid") for item in (collect.instances or [])}
    assert instance_uuids == {HOST_UUIDS["10.0.1.10"], HOST_UUIDS["10.0.1.12"]}
    assert collect.ip_range in ("", None)
    assert delete.call_count == 1
    assert push.call_count == 2


def test_existing_collect_instance_is_skipped(mocker):
    _patch_side_effects(mocker)
    task = _task()
    execution, hits = _execution_with_hits(task, ["10.0.1.10"])
    CollectModels.objects.create(
        name="existing",
        task_type="snmp",
        driver_type="protocol",
        model_id="network",
        is_system=False,
        cycle_value_type="cycle",
        instances=[{"inst_uuid": HOST_UUIDS["10.0.1.10"]}],
        team=[1],
    )

    result = ScanCollectGenerateService.generate(execution, [hits[0].id])

    assert result["skipped"] == 1
    assert result["items"][0]["reason"] == "already_on_collect"
    assert CollectModels.objects.filter(name__startswith="scan-gen").count() == 0


def test_no_ci_hit_is_skipped(mocker):
    _patch_side_effects(mocker)
    task = _task()
    execution, hits = _execution_with_hits(task, ["10.0.1.11"])
    hits[0].inst_uuid = ""
    hits[0].save(update_fields=["inst_uuid"])

    result = ScanCollectGenerateService.generate(execution, [hits[0].id])

    assert result["skipped"] == 1
    assert result["items"][0]["reason"] == "no_ci"
    assert CollectModels.objects.count() == 0


def test_credential_already_hit_is_skipped(mocker):
    _patch_side_effects(mocker)
    task = _task()
    execution, hits = _execution_with_hits(task, ["10.0.1.20"])
    other = CollectModels.objects.create(
        name="other-collect",
        task_type="snmp",
        driver_type="protocol",
        model_id="network",
        cycle_value_type="cycle",
        team=[1],
    )
    CollectTaskCredentialHit.objects.create(
        task=other,
        object_key="host:10.0.1.20",
        credential_id="cred-snmp-1",
        status=CollectTaskCredentialHit.STATUS_SUCCESS,
    )

    result = ScanCollectGenerateService.generate(execution, [hits[0].id])

    assert result["skipped"] == 1
    assert result["items"][0]["reason"] == "credential_already_hit"


def test_regenerate_claims_when_scan_collect_already_hit(mocker, authenticated_user):
    """同扫描任务已采过凭据时：若 hit 尚未回写 collect_task_id，仍应同步并认领。"""
    fake_graph = _patch_side_effects(mocker)
    mocker.patch.object(CollectModelService, "push_butch_node_params")
    mocker.patch.object(CollectModelService, "delete_butch_node_params")
    task = _task()
    execution, hits = _execution_with_hits(task, ["10.0.1.10"])
    request = _request(authenticated_user)

    ScanCollectGenerateService.generate(execution, [hits[0].id], operator="alice", request=request)
    collect = CollectModels.objects.get()
    CollectTaskCredentialHit.objects.create(
        task=collect,
        object_key="host:10.0.1.10",
        credential_id="cred-snmp-1",
        status=CollectTaskCredentialHit.STATUS_SUCCESS,
    )
    collect.input_method = CollectInputMethod.MANUAL
    collect.save(update_fields=["input_method"])
    # 模拟旧数据未回写 collect_task_id，仍走同步路径。
    ScanHit.objects.filter(pk=hits[0].id).update(collect_task_id=None)
    fake_graph.set_entity_properties.reset_mock()

    result = ScanCollectGenerateService.generate(execution, [hits[0].id], operator="alice", request=request)

    assert result["created"] == 0
    assert result["skipped"] == 0
    assert result["appended"] == 1
    assert CollectModels.objects.count() == 1
    collect.refresh_from_db()
    assert collect.input_method == CollectInputMethod.AUTO
    fake_graph.set_entity_properties.assert_called_once()
    assert fake_graph.set_entity_properties.call_args[0][2] == {"collect_task": str(collect.id)}
    hits[0].refresh_from_db()
    assert hits[0].collect_task_id == collect.id


def test_repeat_generate_skips_when_collect_task_id_recorded(mocker, authenticated_user):
    _patch_side_effects(mocker)
    mocker.patch.object(CollectModelService, "push_butch_node_params")
    mocker.patch.object(CollectModelService, "delete_butch_node_params")
    create = mocker.spy(CollectModelService, "create")
    task = _task()
    execution, hits = _execution_with_hits(task, ["10.0.1.10"])
    request = _request(authenticated_user)

    first = ScanCollectGenerateService.generate(execution, [hits[0].id], operator="alice", request=request)
    assert first["created"] == 1
    collect = CollectModels.objects.get()
    hits[0].refresh_from_db()
    assert hits[0].collect_task_id == collect.id
    assert create.call_count == 1

    second = ScanCollectGenerateService.generate(execution, [hits[0].id], operator="alice", request=request)

    assert second["created"] == 0
    assert second["skipped"] == 1
    assert second["items"][0]["reason"] == "already_generated"
    assert second["items"][0]["collect_task_id"] == collect.id
    assert create.call_count == 1
    assert CollectModels.objects.count() == 1


def test_normalize_influxdb_credential_keeps_allowed_fields_only():
    normalized = _normalize_credential_item(
        "influxdb",
        {
            "credential_id": "cred-inf-1",
            "scheme": "https",
            "port": "8086",
            "verify_tls": True,
            "token": "op-token",
            "_client_id": "client-1",
            "username": "must-drop",
        },
    )
    assert normalized == {
        "credential_id": "cred-inf-1",
        "scheme": "https",
        "port": 8086,
        "verify_tls": True,
        "token": "op-token",
    }


def test_influxdb_hits_create_one_task_per_endpoint(mocker, authenticated_user):
    _patch_side_effects(mocker)
    mocker.patch.object(CollectModelService, "push_butch_node_params")
    mocker.patch.object(CollectModelService, "delete_butch_node_params")
    create = mocker.spy(CollectModelService, "create")
    task = _task(
        families=["influxdb"],
        credentials={
            "influxdb": [
                {
                    "credential_id": "cred-inf-1",
                    "scheme": "http",
                    "port": 8086,
                    "verify_tls": True,
                    "token": "op-token",
                    "_client_id": "client-1",
                }
            ]
        },
    )
    execution, hits = _execution_with_hits(
        task,
        ["10.0.1.60", "10.0.1.61"],
        family="influxdb",
        protocol="influxdb",
        port=8086,
        credential_id="cred-inf-1",
        cmdb_model_id="influxdb",
        uuids=INFLUX_UUIDS,
    )

    result = ScanCollectGenerateService.generate(
        execution,
        [hit.id for hit in hits],
        operator="alice",
        request=_request(authenticated_user),
    )

    assert result["created"] == 2
    assert result["failed"] == 0
    assert create.call_count == 2
    collects = list(CollectModels.objects.order_by("id"))
    assert len(collects) == 2
    uuids = {INFLUX_UUIDS["10.0.1.60"], INFLUX_UUIDS["10.0.1.61"]}
    for collect in collects:
        assert collect.model_id == "influxdb"
        assert collect.task_type == "protocol"
        assert collect.input_method == CollectInputMethod.AUTO
        assert collect.ip_range in ("", None)
        assert len(collect.instances) == 1
        assert collect.instances[0]["inst_uuid"] in uuids
        assert collect.instances[0]["model_id"] == "influxdb"
        creds = collect.decrypt_credentials
        assert len(creds) == 1
        assert creds[0]["credential_id"] == "cred-inf-1"
        assert "_client_id" not in creds[0]
        assert "username" not in creds[0]
        runner = BaseCollect(instance_id=None, task=collect)
        assert runner.model_id == "influxdb"


def test_influxdb_regenerate_reuses_same_endpoint_task(mocker, authenticated_user):
    fake_graph = _patch_side_effects(mocker)
    mocker.patch.object(CollectModelService, "push_butch_node_params")
    mocker.patch.object(CollectModelService, "delete_butch_node_params")
    task = _task(
        families=["influxdb"],
        credentials={
            "influxdb": [
                {
                    "credential_id": "cred-inf-1",
                    "scheme": "http",
                    "port": 8086,
                    "verify_tls": True,
                }
            ]
        },
    )
    execution, hits = _execution_with_hits(
        task,
        ["10.0.1.60"],
        family="influxdb",
        protocol="influxdb",
        port=8086,
        credential_id="cred-inf-1",
        cmdb_model_id="influxdb",
        uuids=INFLUX_UUIDS,
    )
    request = _request(authenticated_user)

    first = ScanCollectGenerateService.generate(execution, [hits[0].id], operator="alice", request=request)
    assert first["created"] == 1
    collect = CollectModels.objects.get()
    hits[0].refresh_from_db()
    assert hits[0].collect_task_id == collect.id
    fake_graph.set_entity_properties.reset_mock()

    second = ScanCollectGenerateService.generate(execution, [hits[0].id], operator="alice", request=request)

    assert second["created"] == 0
    assert second["skipped"] == 1
    assert second["items"][0]["reason"] == "already_generated"
    assert CollectModels.objects.count() == 1
    collect.refresh_from_db()
    assert collect.instances[0]["inst_uuid"] == INFLUX_UUIDS["10.0.1.60"]
    fake_graph.set_entity_properties.assert_not_called()


def test_host_generate_copies_scan_cloud_region(mocker, authenticated_user):
    _patch_side_effects(mocker)
    mocker.patch.object(CollectModelService, "push_butch_node_params")
    mocker.patch.object(CollectModelService, "delete_butch_node_params")
    task = _task(
        families=["host"],
        cloud_region={"id": 7, "name": "gz"},
        credentials={
            "host": [
                {
                    "credential_id": "cred-ssh-1",
                    "username": "root",
                    "password": "secret",
                    "port": "22",
                }
            ]
        },
    )
    execution, hits = _execution_with_hits(
        task,
        ["10.0.1.70"],
        family="host",
        driver_type="job",
        protocol="host",
        port=22,
        credential_id="cred-ssh-1",
        cmdb_model_id="host",
        uuids=HOST_FAMILY_UUIDS,
    )

    result = ScanCollectGenerateService.generate(
        execution,
        [hits[0].id],
        operator="alice",
        request=_request(authenticated_user),
    )

    assert result["created"] == 1
    collect = CollectModels.objects.get()
    assert collect.model_id == "host"
    assert collect.task_type == "host"
    assert collect.driver_type == "job"
    assert collect.ip_range in ("", None)
    assert collect.instances[0]["inst_uuid"] == HOST_FAMILY_UUIDS["10.0.1.70"]
    assert collect.params["cloud"] == 7
    assert collect.params["cloud_name"] == "gz"
    runner = BaseCollect(instance_id=None, task=collect)
    assert runner.model_id == "host"


def test_two_credentials_same_family_merge_into_one_task(mocker, authenticated_user):
    _patch_side_effects(mocker)
    mocker.patch.object(CollectModelService, "push_butch_node_params")
    mocker.patch.object(CollectModelService, "delete_butch_node_params")
    task = _task(
        credentials={
            "network": [
                {"credential_id": "cred-snmp-1", "version": "v2", "community": "public", "snmp_port": "161"},
                {"credential_id": "cred-snmp-2", "version": "v2", "community": "private", "snmp_port": "161"},
            ]
        }
    )
    execution, hits_a = _execution_with_hits(task, ["10.0.1.10"], credential_id="cred-snmp-1")
    hits_b = []
    family_run = hits_a[0].family_run
    hits_b.append(
        ScanHit.objects.create(
            execution=execution,
            family_run=family_run,
            protocol="network",
            host="10.0.1.12",
            port=161,
            credential_id="cred-snmp-2",
            status=ScanHit.STATUS_SUCCESS,
            cmdb_model_id="switch",
            inst_uuid=HOST_UUIDS["10.0.1.12"],
            snapshot={"host": "10.0.1.12"},
        )
    )

    result = ScanCollectGenerateService.generate(
        execution,
        [hits_a[0].id, hits_b[0].id],
        operator="alice",
        request=_request(authenticated_user),
    )

    assert result["failed"] == 0
    assert CollectModels.objects.count() == 1
    collect = CollectModels.objects.get()
    cred_ids = {item["credential_id"] for item in collect.decrypt_credentials}
    assert cred_ids == {"cred-snmp-1", "cred-snmp-2"}
    instance_uuids = {item.get("inst_uuid") for item in (collect.instances or [])}
    assert instance_uuids == {HOST_UUIDS["10.0.1.10"], HOST_UUIDS["10.0.1.12"]}
    runner = BaseCollect(instance_id=None, task=collect)
    assert runner.model_id == "network"


def test_scan_generate_allows_more_than_three_credentials(mocker, authenticated_user):
    _patch_side_effects(mocker)
    mocker.patch.object(CollectModelService, "push_butch_node_params")
    mocker.patch.object(CollectModelService, "delete_butch_node_params")
    extra_hosts = {
        "10.0.1.30": "aaaaaaa1-1111-4111-8111-111111111111",
    }
    ALL_UUIDS.update(extra_hosts)
    HOST_UUIDS.update(extra_hosts)
    extra_hosts = {
        "10.0.1.30": "aaaaaaa1-1111-4111-8111-111111111111",
    }
    ALL_UUIDS.update(extra_hosts)
    HOST_UUIDS.update(extra_hosts)
    credentials = [{"credential_id": f"cred-snmp-{index}", "version": "v2", "community": f"c{index}", "snmp_port": "161"} for index in range(1, 5)]
    task = _task(credentials={"network": credentials})
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_COMPLETED)
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="network",
        driver_type="protocol",
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    hosts = ["10.0.1.10", "10.0.1.12", "10.0.1.11", "10.0.1.20"]
    hits = []
    for index, host in enumerate(hosts, start=1):
        hits.append(
            ScanHit.objects.create(
                execution=execution,
                family_run=family_run,
                protocol="network",
                host=host,
                port=161,
                credential_id=f"cred-snmp-{index}",
                status=ScanHit.STATUS_SUCCESS,
                cmdb_model_id="switch",
                inst_uuid=HOST_UUIDS[host],
                snapshot={"host": host},
            )
        )

    result = ScanCollectGenerateService.generate(
        execution,
        [hit.id for hit in hits],
        operator="alice",
        request=_request(authenticated_user),
    )

    assert result["failed"] == 0
    collect = CollectModels.objects.get()
    assert len(collect.decrypt_credentials) == 4
    assert collect.ip_range in ("", None)
    assert len(collect.instances) == 4
