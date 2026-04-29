meta:
  schema_version: "1.0.0"
  object_counts:
    namespaces: 0
    datasources: 0
    dashboards: 1
    topologies: 0
    architectures: 0

dashboards:
  - key: "dashboard::${OA_DASHBOARD_NAME}"
    name: "${OA_DASHBOARD_NAME}"
    desc: "${OA_DASHBOARD_DESC}"
    filters: {}
    other: {}
    view_sets:
${OA_VIEW_SETS_YAML}
