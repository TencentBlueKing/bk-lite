from django.core.management import BaseCommand

from apps.opspilot.services.skill_template_catalog import SkillTemplateCatalogService


class Command(BaseCommand):
    help = "同步内置智能体模板，保留已有智能体和工作台"

    def handle(self, *args, **options):
        templates = SkillTemplateCatalogService().sync()
        self.stdout.write(self.style.SUCCESS(f"内置智能体模板已同步，共 {len(templates)} 个"))
