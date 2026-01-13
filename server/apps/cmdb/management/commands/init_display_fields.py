# -- coding: utf-8 --
"""
初始化 _display 字段的 management 命令

使用方法：
    python manage.py init_display_fields

功能：
    1. 为所有模型批量添加 _display 字段定义
    2. 为所有实例批量生成 _display 字段值
    3. 支持 organization/user/enum 三种字段类型

注意事项：
    - 此命令会修改数据库，建议先备份
    - 执行时间取决于数据量，请耐心等待
    - 支持幂等操作，可多次执行
"""

from django.core.management.base import BaseCommand
from apps.cmdb.display_field import DisplayFieldInitializer
from apps.core.logger import cmdb_logger as logger


class Command(BaseCommand):
    help = '初始化所有模型和实例的 _display 字段（用于全文检索）'
    
    def add_arguments(self, parser):
        """添加命令行参数"""
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='试运行模式，不实际修改数据（仅输出日志）'
        )
    
    def handle(self, *args, **options):
        """执行命令"""
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('【试运行模式】不会实际修改数据')
            )
            logger.warning("[InitDisplayFields] 试运行模式（功能暂未实现）")
        
        self.stdout.write(
            self.style.SUCCESS('开始初始化 _display 字段...')
        )
        
        try:
            # 执行初始化
            initializer = DisplayFieldInitializer()
            result = initializer.initialize_all()
            
            # 输出结果
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n{'='*60}\n"
                        f"✅ 初始化完成！\n"
                        f"{'='*60}\n"
                        f"  模型数: {result['models_processed']}\n"
                        f"  实例数: {result['instances_processed']}\n"
                        f"  错误数: {len(result['errors'])}\n"
                        f"{'='*60}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"\n{'='*60}\n"
                        f"❌ 初始化失败！\n"
                        f"{'='*60}\n"
                        f"  模型数: {result['models_processed']}\n"
                        f"  实例数: {result['instances_processed']}\n"
                        f"  错误数: {len(result['errors'])}\n"
                        f"{'='*60}"
                    )
                )
                
                # 输出错误详情
                if result['errors']:
                    self.stdout.write(self.style.ERROR('\n错误详情:'))
                    for error in result['errors']:
                        self.stdout.write(self.style.ERROR(f"  - {error}"))
            
            # 输出提示
            self.stdout.write('\n')
            self.stdout.write('详细日志请查看日志文件')
            
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING('\n\n操作已取消')
            )
            logger.warning("[InitDisplayFields] 用户取消操作")
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n\n执行失败: {e}')
            )
            logger.error(f"[InitDisplayFields] 执行异常: {e}", exc_info=True)
            raise
