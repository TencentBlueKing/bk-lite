"""播种内置技能包（support-files → 磁盘存储 + SkillPackage 表）。"""

from django.core.management import BaseCommand

from apps.opspilot.services.skill_package.builtin_seed import seed_all_builtin_skill_packages


class Command(BaseCommand):
    help = "从 support-files/skill_packages 同步内置技能包到本地存储与数据库"

    def handle(self, *args, **options):
        self.stdout.write("正在同步内置技能包...")
        results = seed_all_builtin_skill_packages()
        if not results:
            self.stdout.write(self.style.WARNING("未发现可播种的内置技能包目录"))
            return
        for item in results:
            action = "创建" if item.created else "更新"
            self.stdout.write(self.style.SUCCESS(f"{action}: {item.package_id}@{item.version} -> {item.storage_path}"))
        self.stdout.write(self.style.SUCCESS(f"内置技能包同步完成，共 {len(results)} 个"))
