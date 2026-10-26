from django.core.management.base import BaseCommand, CommandError

from apps.system_mgmt.services.itsm_system_token import ItsmSystemTokenError, get_or_create_itsm_token


class Command(BaseCommand):
    help = "用传入的密钥初始化 ITSM 系统密钥；目标行密钥不一致时替换为传入值"

    def add_arguments(self, parser):
        parser.add_argument("--key", required=True, help="ITSM 系统密钥明文")

    def handle(self, *args, **options):
        try:
            result = get_or_create_itsm_token(options["key"])
        except ItsmSystemTokenError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(result)
