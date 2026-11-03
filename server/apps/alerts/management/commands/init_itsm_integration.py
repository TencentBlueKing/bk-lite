from django.core.management.base import BaseCommand

from apps.alerts.constants.constants import DEFAULT_GROUP_ID
from apps.alerts.models.itsm import AlertItsmIntegration
from apps.core.openapi.async_callback import default_public_origin


class Command(BaseCommand):
    help = "初始化告警中心 ITSM 集成默认地址"

    def handle(self, *args, **options):
        url = default_public_origin().rstrip("/") + "/openapi/v1/itsm/openapi/v1"
        _, created = AlertItsmIntegration.objects.get_or_create(
            team_id=DEFAULT_GROUP_ID,
            defaults={"name": "ITSM", "enabled": False, "config": {"url": url, "ca_pem": "", "failure_notification": {}}, "encrypted_token": ""},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"已初始化告警 ITSM 集成默认地址: {url}"))
