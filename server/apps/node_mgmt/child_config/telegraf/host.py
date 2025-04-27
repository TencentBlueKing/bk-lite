import ast
from string import Template

from apps.node_mgmt.models.sidecar import CollectorConfiguration, ChildConfig

CONFIG_MAP = {

    "cpu":"""[[inputs.cpu]]
    percpu = true
    totalcpu = true
    collect_cpu_time = false
    report_active = false
    core_tags = false
    interval = "${interval}s"
    [inputs.cpu.tags]
        instance_id = "${instance_id}"
        instance_type = "${instance_type}"
        collect_type = "host"
        config_type = "cpu" """,

    "disk": """[[inputs.disk]]
    ignore_fs = ["tmpfs", "devtmpfs", "devfs", "iso9660", "overlay", "aufs", "squashfs"]
    interval = "${interval}s"
    [inputs.disk.tags]
        instance_id = "${instance_id}"
        instance_type = "${instance_type}"
        collect_type = "host"
        config_type = "disk" """,

    "diskio": """[[inputs.diskio]]
    interval = "${interval}s"
    [inputs.diskio.tags]
        instance_id = "${instance_id}"
        instance_type = "${instance_type}"
        collect_type = "host"
        config_type = "diskio" """,

    "mem": """[[inputs.mem]]
    interval = "${interval}s"
    [inputs.mem.tags]
        instance_id = "${instance_id}"
        instance_type = "${instance_type}"
        collect_type = "host"
        config_type = "mem" """,

    "net": """[[inputs.net]]
    interval = "${interval}s"
    [inputs.net.tags]
        instance_id = "${instance_id}"
        instance_type = "${instance_type}"
        collect_type = "host"
        config_type = "net" """,

    "processes": """[[inputs.processes]]
    interval = "${interval}s"
    [inputs.processes.tags]
        instance_id = "${instance_id}"
        instance_type = "${instance_type}"
        collect_type = "host"
        config_type = "processes" """,

    "system": """[[inputs.system]]
    interval = "${interval}s"
    [inputs.system.tags]
        instance_id = "${instance_id}"
        instance_type = "${instance_type}"
        collect_type = "host"
        config_type = "system" """,
}

class HostConfig:
    @staticmethod
    def patch_set_node_config(nodes: list):
        """批量添加节点配置"""
        node_objs, base_config_ids = [], []

        for node in nodes:
            node_id = node["id"]
            node_configs = node["configs"]
            base_config = CollectorConfiguration.objects.filter(nodes__id=node_id, collector__name="Telegraf").first()
            base_config_id = base_config.id
            base_config_ids.append(base_config_id)
            for node_config in node_configs:

                content = CONFIG_MAP[node_config["type"]]
                template = Template(content)
                _node_config = node_config.copy()
                _node_config["instance_id"] = ast.literal_eval(_node_config["instance_id"])[0]
                content = template.safe_substitute(_node_config)
                node_objs.append(ChildConfig(
                    collect_type="host",
                    config_type=node_config["type"],
                    content=content,
                    collector_config_id=base_config_id,
                    collect_instance_id=node_config["instance_id"],
                ))

        old_child_configs = ChildConfig.objects.filter(collector_config_id__in=base_config_ids, collect_type="host")
        old_child_map = {(i.collect_type, i.config_type, i.collect_instance_id): i for i in old_child_configs}
        creates, updates = [], []
        for node_obj in node_objs:
            if (node_obj.collect_type, node_obj.config_type, node_obj.collect_instance_id) in old_child_map:
                old_child_map[(
                node_obj.collect_type, node_obj.config_type, node_obj.collect_instance_id)].content = node_obj.content
                updates.append(
                    old_child_map[(node_obj.collect_type, node_obj.config_type, node_obj.collect_instance_id)])
            else:
                creates.append(node_obj)

        if creates:
            ChildConfig.objects.bulk_create(creates, batch_size=100)

        if updates:
            ChildConfig.objects.bulk_update(updates, ["content"])
