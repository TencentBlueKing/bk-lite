PACKAGE_KEYS = frozenset(
    {
        "meta",
        "datasources",
        "namespaces",
        "dashboards",
        "topologies",
        "architectures",
        "screens",
        "reports",
        "network_topologies",
    }
)

WIDGET_CHART_TYPES = frozenset(
    {
        "line",
        "pie",
        "bar",
        "table",
        "single",
        "topN",
        "gauge",
        "eventTable",
        "eventTimeline",
        "cardList",
        "radar",
        "room3D",
        "networkStatusTopology",
        "multiValue",
        "text",
        "topologyMap",
        "nodeGraph",
    }
)

HISTORY_LIMIT = 20
CHECKPOINT_LABEL_MAX_LENGTH = 30
