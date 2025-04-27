import ast
from string import Template

from apps.node_mgmt.models.sidecar import CollectorConfiguration, ChildConfig

CONFIG_MAP = {
    "ping": """[[inputs.ping]]
    urls = ["${url}"]
    interval = "${interval}s"
    [inputs.ping.tags]
        instance_id = "${instance_id}"
        instance_type = "${instance_type}"
        collect_type = "ping" """,
    }


class PingConfig:
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
                    collect_type="ping",
                    config_type=node_config["type"],
                    content=content,
                    collector_config_id=base_config_id,
                    collect_instance_id=node_config["instance_id"],
                ))

        old_child_configs = ChildConfig.objects.filter(collector_config_id__in=base_config_ids, collect_type="ping")
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
