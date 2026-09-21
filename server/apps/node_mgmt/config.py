# -- coding: utf-8 --

from apps.core.celery_schedule import beat_crontab

CELERY_BEAT_SCHEDULE = {
    'check_all_region_services': {
        'task': 'apps.node_mgmt.tasks.cloudregion.check_all_region_services',
        'schedule': beat_crontab(minute='*/15'),  # 每5分钟执行一次
    },
    'discover_node_versions': {
        'task': 'apps.node_mgmt.tasks.version_discovery.discover_node_versions',
        'schedule': beat_crontab(minute='*/30'),  # 每30分钟执行一次
    },
    'restart_failed_collectors': {
        'task': 'apps.node_mgmt.tasks.collector_auto_restart.restart_failed_collectors',
        'schedule': beat_crontab(minute='0'),  # 每小时扫描一次异常采集器并下发 restart
    },
}
