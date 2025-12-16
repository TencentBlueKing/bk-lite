# -- coding: utf-8 --
# export_source_api_data.py
"""
导出数据源API数据到JSON文件
用于将数据库中的DataSourceAPIModel数据导出为服务内置的JSON格式
"""

import json
from pathlib import Path

from django.core.management import BaseCommand

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.core.logger import operation_analysis_logger as logger


class Command(BaseCommand):
    help = "导出数据源API数据到JSON文件"

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='source_api_export.json',
            help='输出文件路径(默认: source_api_export.json)',
        )
        parser.add_argument(
            '--indent',
            type=int,
            default=2,
            help='JSON缩进空格数(默认: 2)',
        )
        parser.add_argument(
            '--active-only',
            action='store_true',
            dest='active_only',
            help='仅导出启用状态的数据源',
        )
        parser.add_argument(
            '--exclude-builtin',
            action='store_true',
            dest='exclude_builtin',
            help='排除内置数据源(通过created_by=system判断)',
        )

    def handle(self, *args, **options):
        output_file = options['output']
        indent = options['indent']
        active_only = options['active_only']
        exclude_builtin = options['exclude_builtin']

        logger.info("===开始导出数据源API数据===")
        self.stdout.write(self.style.SUCCESS("开始导出数据源API数据"))

        try:
            # 构建查询条件
            queryset = DataSourceAPIModel.objects.all()
            
            if active_only:
                queryset = queryset.filter(is_active=True)
                logger.info("仅导出启用状态的数据源")
            
            if exclude_builtin:
                queryset = queryset.exclude(created_by='system')
                logger.info("排除内置数据源")

            # 转换为服务内置格式
            export_data = []
            for api_obj in queryset:
                data = {
                    "name": api_obj.name,
                    "desc": api_obj.desc or "",
                    "rest_api": api_obj.rest_api,
                    "params": api_obj.params or []
                }
                export_data.append(data)

            # 确定输出路径
            output_path = Path(output_file)
            if not output_path.is_absolute():
                # 如果是相对路径，放到support-files目录下
                support_files_dir = Path(__file__).resolve().parent.parent.parent / 'support-files'
                output_path = support_files_dir / output_file

            # 确保目录存在
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入JSON文件
            with output_path.open('w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=indent)

            success_msg = f"成功导出 {len(export_data)} 条数据源API数据到: {output_path}"
            self.stdout.write(self.style.SUCCESS(success_msg))
            logger.info(f"==={success_msg}===")

        except Exception as e:
            error_msg = f"导出数据源API数据失败: {e}"
            logger.error(error_msg, exc_info=True)
            self.stdout.write(self.style.ERROR(error_msg))
            raise

