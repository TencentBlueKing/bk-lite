from django.core.management import BaseCommand

from apps.core.logger import system_mgmt_logger as logger


class Command(BaseCommand):
    help = "关闭国密传输开关"

    def handle(self, *args, **options):
        try:
            from apps.core.enterprise.gm_transport import disable_gm_transport_setting
        except ImportError:
            return
        before = disable_gm_transport_setting()
        self.stdout.write(f"{before} -> 0")
        logger.info("event=gm_transport_disabled before=%s after=0", before)
