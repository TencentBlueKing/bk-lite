from django.core.management import BaseCommand

from apps.opspilot.services.skill_template_catalog import SkillTemplateCatalogService


class Command(BaseCommand):
    help = "同步内置智能体模板"

    def handle(self, *args, **options):
        SkillTemplateCatalogService().sync()
