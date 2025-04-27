import ast
from string import Template

from apps.node_mgmt.models.sidecar import CollectorConfiguration, ChildConfig

CONFIG_MAP = {
    "elasticsearch": """[[inputs.elasticsearch]]
    servers = ["${server}"]
    username = "${username}"
    password = "${password}"
    interval = "${interval}s"
    [inputs.elasticsearch.tags]
        instance_id = "${instance_id}"
        instance_type = "${instance_type}"
        collect_type = "database" """,

    "mongodb": """[[inputs.mongodb]]
    servers = ["mongodb://${host}:${port}/?connect=direct"]
    interval = "${interval}s"
    [inputs.mongodb.tags]
        instance_id = "${instance_id}"
        instance_type = "${instance_type}"
        collect_type = "database" """,

    "mysql": """[[inputs.mysql]]
    servers = ["${username}:${password}@tcp(${host}:${port})/?tls=false"]
    metric_version = 2
    interval = "${interval}s"
    [inputs.mysql.tags]
        instance_id = "${instance_id}"
        instance_type = "${instance_type}"
        collect_type = "database" """,

    "postgres": """[[inputs.postgresql]]
    address = "host=${host} port=${port} user=${username} password=${password} sslmode=disable"
    ignored_databases = ["template0", "template1"]
    interval = "${interval}s"
    [inputs.postgresql.tags]
        instance_id = "${instance_id}"
        instance_type = "${instance_type}"
        collect_type = "database" """,

    "redis": """[[inputs.redis]]
    servers = ["tcp://${host}:${port}"]
    username = "${username}"
    password = "${password}"
    interval = "${interval}s"
    [inputs.redis.tags]
        instance_id = "${instance_id}"
        instance_type = "${instance_type}"
        collect_type = "database" """,

    "sqlserver": """[[inputs.sqlserver]]
    servers = ["Server=${host};Port=${port};User Id=${username};Password=${password};app name=telegraf;log=1;"]
    database_type = "SQLServer"
    exclude_query = ["SQLServerAvailabilityReplicaStates", "SQLServerDatabaseReplicaStates"]
    interval = "${interval}s"
    [inputs.sqlserver.tags]
        instance_id = "${instance_id}"
        instance_type = "${instance_type}"
        collect_type = "database" """,
}


class DataBaseConfig:
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
                    collect_type="database",
                    config_type=node_config["type"],
                    content=content,
                    collector_config_id=base_config_id,
                    collect_instance_id=node_config["instance_id"],
                ))

        old_child_configs = ChildConfig.objects.filter(collector_config_id__in=base_config_ids, collect_type="database")
        old_child_map = {(i.collect_type, i.config_type, i.collect_instance_id): i for i in old_child_configs}
        creates, updates = [], []
        for node_obj in node_objs:
            if (node_obj.collect_type, node_obj.config_type, node_obj.collect_instance_id) in old_child_map:
                old_child_map[(node_obj.collect_type, node_obj.config_type, node_obj.collect_instance_id)].content = node_obj.content
                updates.append(old_child_map[(node_obj.collect_type, node_obj.config_type, node_obj.collect_instance_id)])
            else:
                creates.append(node_obj)

        if creates:
            ChildConfig.objects.bulk_create(creates, batch_size=100)

        if updates:
            ChildConfig.objects.bulk_update(updates, ["content"])
