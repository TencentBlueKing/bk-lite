from apps.monitor.services.node_mgmt import InstanceConfigService


def test_create_instances_calls_backfill_when_cmdb_id_present(mocker):
    mocker.patch.object(InstanceConfigService, "_sync_existing_instance_attrs", return_value=0)
    mocker.patch.object(InstanceConfigService, "_batch_create_default_rules", return_value=[])
    mocker.patch.object(
        InstanceConfigService,
        "_build_instance_objects",
        return_value=([], [], ["m-1"]),
    )
    hook = mocker.patch.object(InstanceConfigService, "_backfill_cmdb_monitor_ids")

    InstanceConfigService._create_instances_in_db(
        [{"instance_id": "m-1", "cmdb_id": "ci-1", "group_ids": [1]}],
        [],
        12,
        actor_context={"username": "alice"},
    )
    hook.assert_called_once()
    pairs_source = hook.call_args.args[0]
    assert pairs_source[0]["cmdb_id"] == "ci-1"


def test_backfill_hook_skips_when_module_link_not_installed(mocker):
    mocker.patch("django.apps.apps.is_installed", return_value=False)
    fn = mocker.patch("apps.module_link.services.backfill.backfill_monitor_ids")
    InstanceConfigService._backfill_cmdb_monitor_ids(
        [{"instance_id": "m-1", "cmdb_id": "ci-1"}],
        actor_context={"username": "alice"},
    )
    fn.assert_not_called()


def test_backfill_hook_forwards_pairs(mocker):
    mocker.patch("django.apps.apps.is_installed", return_value=True)
    fn = mocker.patch("apps.module_link.services.backfill.backfill_monitor_ids")
    actor = {"username": "alice"}
    InstanceConfigService._backfill_cmdb_monitor_ids(
        [
            {"instance_id": "m-1", "cmdb_id": "ci-1"},
            {"instance_id": "m-2"},
            {"instance_id": "", "cmdb_id": "ci-3"},
        ],
        actor_context=actor,
    )
    fn.assert_called_once_with([("ci-1", "m-1")], actor)
