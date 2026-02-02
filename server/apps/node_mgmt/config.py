# -- coding: utf-8 --

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'check_all_region_services': {
        'task': 'apps.node_mgmt.tasks.cloudregion.check_all_region_services',
        'schedule': crontab(minute='*/15'),  # 每5分钟执行一次
    },
    'discover_node_versions': {
        'task': 'apps.node_mgmt.tasks.version_discovery.discover_node_versions',
        'schedule': crontab(minute='*/30'),  # 每30分钟执行一次
    },
}
