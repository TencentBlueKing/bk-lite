monitor_object_id: ${MYSQL_MONITOR_OBJECT_ID}
monitor_plugin_id: ${MYSQL_MONITOR_PLUGIN_ID}
collector: Telegraf
collect_type: database
configs:
  - type: mysql
    interval: ${MYSQL_INTERVAL_SECONDS}
instances:
  - ${MYSQL_INSTANCE_ID_LINE}
    instance_name: "${MYSQL_INSTANCE_NAME}"
    instance_type: "${MYSQL_INSTANCE_TYPE}"
    group_ids:
      - ${MYSQL_GROUP_ID}
    node_ids:
      - "${MYSQL_NODE_ID}"
    host: "${MYSQL_HOST}"
    port: ${MYSQL_PORT}
    username: "${MYSQL_USERNAME}"
    ENV_PASSWORD: "${MYSQL_PASSWORD}"
    interval: ${MYSQL_INTERVAL_SECONDS}
