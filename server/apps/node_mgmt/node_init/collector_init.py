from apps.node_mgmt.models.sidecar import Collector


COLLECTORS = [
    {
        "id": "natsexecutor_linux",
        "name": "NATS-Executor",
        "controller_default_run": True,
        "icon": "caijixinxi",
        "node_operating_system": "linux",
        "service_type": "exec",
        "executable_path": "/opt/fusion-collectors/bin/nats-executor",
        "execute_parameters": "--config %s",
        "validation_parameters": "",
        "default_template": "",
        "introduction": "NATS Executor is a task scheduling and management tool that automates data storage, backup, and distributed file processing tasks.",
        "enabled_default_config": True,
        "default_config": {
        "nats": """nats_urls: "nats://${NATS_USERNAME}:${NATS_PASSWORD}@${NATS_SERVERS}"
nats_instanceId: "${node.id}"
nats_conn_timeout: 600
tls_enabled: "${TLS_ENABLED}" 
tls_skip_verify: "${TLS_SKIP_VERIFY}"
tls_hostname: "${TLS_HOSTNAME}"
tls_ca_file: "${TLS_CA_FILE}"
tls_cert_file: "${TLS_CERT_FILE}"
tls_key_file: "${TLS_KEY_FILE}"
""",
        }
    },
    {
        "id": "natsexecutor_windows",
        "name": "NATS-Executor",
        "controller_default_run": True,
        "icon": "caijixinxi",
        "node_operating_system": "windows",
        "service_type": "exec",
        "executable_path": "C:\\bklite\\fusion-collectors\\bin\\nats-executor.exe",
        "execute_parameters": "--config %s",
        "validation_parameters": "",
        "default_template": "",
        "introduction": "NATS Executor is a task scheduling and management tool that automates data storage, backup, and distributed file processing tasks.",
        "enabled_default_config": True,
        "default_config": {
        "nats": """nats_urls: "nats://${NATS_USERNAME}:${NATS_PASSWORD}@${NATS_SERVERS}"
nats_instanceId: "${node.id}"
nats_conn_timeout: 600
tls_enabled: ${TLS_ENABLED}
tls_skip_verify: ${TLS_SKIP_VERIFY}
tls_hostname: "${TLS_HOSTNAME}"
tls_ca_file: "${TLS_CA_FILE}"
tls_cert_file: "${TLS_CERT_FILE}"
tls_key_file: "${TLS_KEY_FILE}"
""",
        }
    },
]


def import_collector(collectors):
    old_collector = Collector.objects.all()
    old_collector_set = {i.id for i in old_collector}

    create_collectors, update_collectors = [], []

    for collector_info in collectors:
        if collector_info["id"] in old_collector_set:
            update_collectors.append(collector_info)
        else:
            create_collectors.append(collector_info)

    if create_collectors:
        Collector.objects.bulk_create([Collector(**i) for i in create_collectors])

    if update_collectors:
        Collector.objects.bulk_update([Collector(**i) for i in update_collectors],
                                      ["service_type", "executable_path", "execute_parameters", "validation_parameters",
                                       "default_template", "introduction", "enabled_default_config", "default_config",])


def collector_init():
    """
    初始化采集器
    """
    import_collector(COLLECTORS)
