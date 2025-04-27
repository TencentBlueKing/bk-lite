from apps.node_mgmt.models.sidecar import Collector


COLLECTORS = [
    {
        "id": "telegraf_linux",
        "name": "Telegraf",
        "controller_default_run": False,
        "icon": "shujucaiji ",
        "node_operating_system": "linux",
        "service_type": "exec",
        "executable_path": "/opt/fusion-collectors/bin/telegraf",
        "execute_parameters": "--config %s",
        "validation_parameters": "--config %s --test",
        "default_template": "",
        "introduction": "Telegraf is a lightweight and efficient metrics collector that supports real-time collection, processing, and transmission of multi-source data, widely used in monitoring and data analysis scenarios."
    },
    {
        "id": "telegraf_windows",
        "name": "Telegraf",
        "controller_default_run": False,
        "icon": "shujucaiji ",
        "node_operating_system": "windows",
        "service_type": "exec",
        "executable_path": "C:\\Program Files\\Telegraf\\telegraf.exe",
        "execute_parameters": "-config C:\\Program Files\\Telegraf\\telegraf.conf",
        "validation_parameters": "-test -config C:\\Program Files\\Telegraf\\telegraf.conf",
        "default_template": "",
        "introduction": "Telegraf is a lightweight and efficient metrics collector that supports real-time collection, processing, and transmission of multi-source data, widely used in monitoring and data analysis scenarios."
    },
    {
        "id": "natsexecutor_linux",
        "name": "NATS-Executor",
        "controller_default_run": True,
        "icon": "caijixinxi ",
        "node_operating_system": "linux",
        "service_type": "exec",
        "executable_path": "/opt/fusion-collectors/bin/nats-executor",
        "execute_parameters": "--config %s",
        "validation_parameters": "",
        "default_template": "",
        "introduction": "NATS Executor is a task scheduling and management tool that automates data storage, backup, and distributed file processing tasks."
    },
    {
        "id": "natsexecutor_windows",
        "name": "NATS-Executor",
        "controller_default_run": True,
        "icon": "caijixinxi ",
        "node_operating_system": "windows",
        "service_type": "exec",
        "executable_path": "C:\\Program Files\\NATS\\nats-executor.exe",
        "execute_parameters": "-config C:\\Program Files\\NATS\\nats-executor.conf",
        "validation_parameters": "",
        "default_template": "",
        "introduction": "NATS Executor is a task scheduling and management tool that automates data storage, backup, and distributed file processing tasks."
    }

]


def collector_init():
    """
    初始化采集器
    """
    old_collector = Collector.objects.all()
    old_collector_set = {i.id for i in old_collector}

    create_collectors, update_collectors = [], []

    for collector_info in COLLECTORS:
        if collector_info["id"] in old_collector_set:
            update_collectors.append(collector_info)
        else:
            create_collectors.append(collector_info)

    if create_collectors:
        Collector.objects.bulk_create([Collector(**i) for i in create_collectors])

    if update_collectors:
        Collector.objects.bulk_update([Collector(**i) for i in update_collectors], ["service_type", "executable_path", "execute_parameters", "validation_parameters", "default_template", "introduction"])
