from celery import shared_task

from apps.core.logger import celery_logger as logger
from apps.monitor.constants.aix_node_exporter import DEFAULT_SCRAPE_PORT, DEFAULT_USERNAME
from apps.monitor.services.aix_node_exporter import AixNodeExporterError, AixNodeExporterService
from apps.rpc.node_mgmt import NodeMgmt


@shared_task
def install_aix_node_exporter(
    child_config_id,
    instance_id,
    node_id,
    host,
    scrape_port=DEFAULT_SCRAPE_PORT,
    username=DEFAULT_USERNAME,
    skip_copy=False,
):
    logger.info(
        "event=aix_node_exporter_install_accepted child_config_id=%s instance_id=%s node_id=%s skip_copy=%s",
        child_config_id,
        instance_id,
        node_id,
        skip_copy,
    )
    try:
        rows = NodeMgmt().get_child_configs_by_ids([child_config_id])
        if not rows:
            raise AixNodeExporterError(
                "child config missing",
                failed_stage="load_credentials",
                error_type="ChildConfigMissing",
            )
        env_config = rows[0].get("env_config") or {}
        persisted_node_id = _env_lookup(env_config, "NODE_ID", child_config_id)
        credentials = AixNodeExporterService.load_credentials(
            env_config,
            child_config_id,
            {"username": username},
        )
        AixNodeExporterService.install(
            node_id=persisted_node_id or node_id,
            host=host,
            username=credentials["username"],
            password=credentials["password"],
            private_key=credentials["private_key"],
            passphrase=credentials["passphrase"],
            scrape_port=scrape_port,
            skip_copy=skip_copy,
        )
    except AixNodeExporterError as exc:
        logger.error(
            "event=aix_node_exporter_install_failed child_config_id=%s instance_id=%s node_id=%s failed_stage=%s error_type=%s",
            child_config_id,
            instance_id,
            node_id,
            exc.failed_stage,
            exc.error_type,
            exc_info=True,
        )
        raise
    except Exception as exc:
        logger.error(
            "event=aix_node_exporter_install_failed child_config_id=%s instance_id=%s node_id=%s failed_stage=install error_type=%s",
            child_config_id,
            instance_id,
            node_id,
            type(exc).__name__,
            exc_info=True,
        )
        raise
    logger.info(
        "event=aix_node_exporter_install_succeeded child_config_id=%s instance_id=%s node_id=%s",
        child_config_id,
        instance_id,
        node_id,
    )
    return {"success": True, "child_config_id": child_config_id}


def _env_lookup(env_config, prefix, config_id):
    return (env_config or {}).get(f"{prefix}__{str(config_id).upper()}")
