from django.core.management import BaseCommand

from apps.opspilot.services.skill_template_catalog import SkillTemplateCatalogService


class Command(BaseCommand):
    help = "用 Kubernetes 助手和 Postgres DB 助手替换智能体模板"

    def handle(self, *args, **options):
        SkillTemplateCatalogService().replace()
        self.stdout.write(self.style.SUCCESS("智能体模板已替换为 Kubernetes 助手和 Postgres DB 助手"))
