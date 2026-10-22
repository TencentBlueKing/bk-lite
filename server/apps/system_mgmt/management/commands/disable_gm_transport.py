from django.core.management import BaseCommand

from apps.core.logger import system_mgmt_logger as logger
from apps.core.services.gm_transport import SETTING_KEY
from apps.system_mgmt.models import SystemSettings


class Command(BaseCommand):
    help = "关闭国密传输开关"

    def handle(self, *args, **options):
        row = SystemSettings.objects.filter(key=SETTING_KEY).first()
        before = "0" if row is None else str(row.value)
        if row is None:
            SystemSettings.objects.create(key=SETTING_KEY, value="0")
        elif before != "0":
            row.value = "0"
            row.save(update_fields=["value"])
        self.stdout.write(f"{before} -> 0")
        logger.info("event=gm_transport_disabled before=%s after=0", before)
