from django.core.management import BaseCommand

from apps.opspilot.services.skill_template_catalog import SkillTemplateCatalogService


class Command(BaseCommand):
    help = "同步内置智能体模板（旧命令入口，不再自动创建工作台）"

    def handle(self, *args, **options):
        SkillTemplateCatalogService().sync()
        self.stdout.write(self.style.SUCCESS("内置智能体模板已同步"))
