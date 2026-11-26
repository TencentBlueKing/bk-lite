from celery import shared_task

from apps.log.services.syslog_source_device import discover_syslog_source_devices as run_syslog_source_device_discovery


@shared_task(name="apps.log.tasks.syslog_source_device.discover_syslog_source_devices")
def discover_syslog_source_devices():
    return run_syslog_source_device_discovery()
