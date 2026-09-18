import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.scan_model import (
    SCAN_AGENT_CREDENTIAL_ID,
    SCAN_MIDDLEWARE_FAMILY,
    SCAN_MIDDLEWARE_TYPES,
    ScanExecution,
    ScanFamilyRun,
    ScanHit,
    ScanTask,
    agent_placeholder_pool,
    default_scan_snmp_version,
    is_agent_credential,
    normalize_scan_families,
    resolve_scan_task_credential,
    scan_driver_type_for_model,
    scan_encrypt_model_id,
    scan_task_type_for_model,
)

pytestmark = pytest.mark.django_db


def test_scan_task_defaults_auto_push_off():
    task = ScanTask.objects.create(
        name="scan-model-probe",
        team=["1"],
        ip_ranges=[],
        families=[],
        credentials={},
    )
    assert task.auto_push_monitor is False
    assert task.auto_generate_collect is False


def test_scan_task_encrypts_credentials_per_family_on_save():
    task = ScanTask.objects.create(
        name="scan-encrypt-probe",
        team=["1"],
        families=["mysql", "network"],
        credentials={
            "mysql": [{"credential_id": "cred-db", "username": "monitor", "password": "db-secret"}],
            "network": [{"credential_id": "cred-snmp", "version": "v2c", "community": "public"}],
        },
    )
    task.refresh_from_db()
    mysql_password = task.credentials["mysql"][0]["password"]
    community = task.credentials["network"][0]["community"]
    assert mysql_password.startswith("enc:")
    assert mysql_password != "db-secret"
    assert community.startswith("enc:")
    assert community != "public"
    assert task.credentials["mysql"][0]["username"] == "monitor"


def test_scan_task_decrypt_credentials_returns_plaintext_per_family():
    task = ScanTask.objects.create(
        name="scan-decrypt-probe",
        team=["1"],
        families=["mysql"],
        credentials={
            "mysql": [{"credential_id": "cred-db", "username": "monitor", "password": "db-secret"}],
        },
    )
    decrypted = task.decrypt_credentials
    assert decrypted["mysql"][0]["password"] == "db-secret"
    assert decrypted["mysql"][0]["username"] == "monitor"
    assert task.credentials["mysql"][0]["password"].startswith("enc:")


def test_scan_execution_and_hit_can_be_created():
    task = ScanTask.objects.create(name="scan-exec-probe", team=["1"])
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_PENDING)
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="mysql",
        driver_type="protocol",
    )
    hit = ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="mysql",
        host="10.0.1.20",
        port=3306,
        credential_id="cred-db",
        status=ScanHit.STATUS_SUCCESS,
    )
    assert execution.claim_token == ""
    assert execution.target_count == 0
    assert family_run.received_count == 0
    assert hit.inst_uuid == ""


def test_middleware_family_normalizes_and_maps_job_plugin():
    assert SCAN_MIDDLEWARE_FAMILY in normalize_scan_families(["middleware", "host"])
    assert SCAN_MIDDLEWARE_TYPES == frozenset({"nginx", "tomcat", "kafka", "zookeeper", "rabbitmq", "consul", "etcd"})
    assert scan_encrypt_model_id("middleware") == "host"
    assert scan_driver_type_for_model("nginx") == CollectDriverTypes.JOB
    assert scan_task_type_for_model("nginx") == CollectPluginTypes.MIDDLEWARE
    assert is_agent_credential({}) is True
    assert is_agent_credential({"credential_id": SCAN_AGENT_CREDENTIAL_ID}) is True
    assert is_agent_credential({"username": "root", "password": "x"}) is False
    assert is_agent_credential({"private_key": "-----BEGIN KEY-----"}) is False
    assert agent_placeholder_pool() == [{"credential_id": SCAN_AGENT_CREDENTIAL_ID}]


def test_resolve_middleware_credential_falls_back_to_host_pool():
    task = ScanTask.objects.create(
        name="scan-mw-resolve",
        team=["1"],
        families=["host", "middleware"],
        credentials={
            "host": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}],
        },
    )
    found = resolve_scan_task_credential(task, "nginx", "cred-ssh")
    assert found["username"] == "root"
    agent = resolve_scan_task_credential(task, "nginx", SCAN_AGENT_CREDENTIAL_ID)
    assert agent == {"credential_id": SCAN_AGENT_CREDENTIAL_ID}


def test_default_scan_snmp_version_fills_ui_default():
    assert default_scan_snmp_version({"community": "public"})["version"] == "v2"
    assert default_scan_snmp_version({"username": "snmpuser"})["version"] == "v3"
    assert default_scan_snmp_version({"version": "v2c", "community": "public"})["version"] == "v2c"
    assert default_scan_snmp_version({"version": "v3", "username": "snmpuser"})["version"] == "v3"
