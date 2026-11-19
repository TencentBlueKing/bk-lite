from io import StringIO

import pytest
from django.core.management import call_command

from apps.monitor.models import CollectConfig, MonitorInstance, MonitorObject


def _object(name="OS"):
    return MonitorObject.objects.create(name=name, level="base")


def _instance(obj, *, instance_id, name, ip="10.0.0.8", cloud_region_id=1, is_deleted=True, is_active=False):
    return MonitorInstance.objects.create(
        id=instance_id,
        name=name,
        monitor_object=obj,
        ip=ip,
        cloud_region_id=cloud_region_id,
        is_deleted=is_deleted,
        is_active=is_active,
    )


def _config(instance, *, config_id, config_type="cpu", executor_node_id="", executor_node_name=""):
    return CollectConfig.objects.create(
        id=config_id,
        monitor_instance=instance,
        collector="Telegraf",
        collect_type="host",
        config_type=config_type,
        file_type="toml",
        executor_node_removed=False,
        executor_node_id=executor_node_id,
        executor_node_name=executor_node_name,
    )


def _run(*args):
    out = StringIO()
    call_command("restore_node_exit_parked_hosts", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_dry_run_does_not_write():
    obj = _object()
    instance = _instance(obj, instance_id="parked-1", name="old-host")
    config = _config(instance, config_id="cfg-1", executor_node_id="node-9", executor_node_name="edge-9")

    text = _run()

    assert "parked-1\told-host\t1\trestorable" in text
    assert "summary\tcandidates=1\trestorable=1\tconflicts=0\tdry-run=true" in text
    instance.refresh_from_db()
    config.refresh_from_db()
    assert instance.is_deleted is True
    assert instance.is_active is False
    assert config.executor_node_removed is False
    assert config.executor_node_id == "node-9"
    assert config.executor_node_name == "edge-9"


@pytest.mark.django_db
def test_apply_restores_without_conflict():
    obj = _object()
    instance = _instance(obj, instance_id="parked-1", name="old-host")
    kept = _config(instance, config_id="cfg-kept", config_type="cpu", executor_node_id="node-9", executor_node_name="edge-9")
    empty = _config(instance, config_id="cfg-empty", config_type="mem")

    text = _run("--apply")

    assert "parked-1\told-host\t2\trestored" in text
    assert "summary\tcandidates=1\trestored=1\tconflicts=0\tdry-run=false" in text
    instance.refresh_from_db()
    kept.refresh_from_db()
    empty.refresh_from_db()
    assert instance.is_deleted is False
    assert instance.is_active is True
    assert kept.executor_node_removed is True
    assert kept.executor_node_id == "node-9"
    assert kept.executor_node_name == "edge-9"
    assert empty.executor_node_removed is True
    assert empty.executor_node_id == ""
    assert empty.executor_node_name == ""


@pytest.mark.django_db
def test_conflict_is_left_untouched():
    obj = _object()
    live = _instance(obj, instance_id="live-1", name="live-host", is_deleted=False, is_active=True)
    parked = _instance(obj, instance_id="parked-1", name="old-host")
    config = _config(parked, config_id="cfg-1")

    text = _run("--apply")

    assert "parked-1\told-host\t1\tconflict:live-1" in text
    assert "summary\tcandidates=1\trestored=0\tconflicts=1\tdry-run=false" in text
    parked.refresh_from_db()
    live.refresh_from_db()
    config.refresh_from_db()
    assert parked.is_deleted is True
    assert parked.is_active is False
    assert config.executor_node_removed is False
    assert live.is_deleted is False
    assert live.is_active is True


@pytest.mark.django_db
def test_soft_deleted_without_config_is_not_candidate():
    obj = _object()
    bare = _instance(obj, instance_id="bare-1", name="bare-host")

    text = _run()

    assert "bare-1" not in text
    assert "summary\tcandidates=0\trestorable=0\tconflicts=0\tdry-run=true" in text
    bare.refresh_from_db()
    assert bare.is_deleted is True
    assert bare.is_active is False


@pytest.mark.django_db
def test_apply_is_idempotent():
    obj = _object()
    instance = _instance(obj, instance_id="parked-1", name="old-host")
    config = _config(instance, config_id="cfg-1", executor_node_id="node-9", executor_node_name="edge-9")

    first = _run("--apply")
    second = _run("--apply")

    assert "parked-1\told-host\t1\trestored" in first
    assert "parked-1" not in second
    assert "summary\tcandidates=0\trestored=0\tconflicts=0\tdry-run=false" in second
    instance.refresh_from_db()
    config.refresh_from_db()
    assert instance.is_deleted is False
    assert instance.is_active is True
    assert config.executor_node_removed is True
    assert config.executor_node_id == "node-9"
    assert config.executor_node_name == "edge-9"
