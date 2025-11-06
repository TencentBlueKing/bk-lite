from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from apps.alerts.models import AggregationRules
from apps.alerts.utils.util import image_to_base64
from apps.core.logger import alert_logger as logger
from apps.alerts.common.rules.rules import NEW_INIT_RULES


class Command(BaseCommand):
    help = '创建内置告警聚合规则'
    base_path = "/apps/alerts/images"

    def add_arguments(self, parser):
        parser.add_argument(
            '--update',
            action='store_true',
            help='强制更新已存在的规则',
        )

    def handle(self, *args, **options):
        update = options['update']
        self.stdout.write('开始创建内置告警聚合规则...')

        try:
            with transaction.atomic():
                # 创建聚合规则
                aggregation_rules = self._create_aggregation_rules(force_update=update)

                self.stdout.write(
                    self.style.SUCCESS(
                        f'成功创建 {len(aggregation_rules)} 个聚合规则'
                    )
                )

        except Exception as e:
            logger.error(f"创建内置规则失败: {str(e)}")
            self.stdout.write(
                self.style.ERROR(f'创建规则失败: {str(e)}')
            )

    def _create_aggregation_rules(self, force_update=False):
        """创建或更新聚合规则"""
        created_count = 0
        updated_count = 0

        # for rule_data in INIT_RULES:
        for rule_data in NEW_INIT_RULES:
            try:
                # 查询规则是否存在
                existing_rule = AggregationRules.objects.filter(rule_id=rule_data['rule_id']).first()

                if existing_rule:
                    if force_update:
                        # 更新现有规则
                        for key, value in rule_data.items():
                            if key != 'rule_id':  # rule_id不能修改
                                setattr(existing_rule, key, value)
                        image = self.get_rule_image(rule_data['rule_id'])
                        if image:
                            setattr(existing_rule, "image", image)
                        else:
                            logger.warning(f"未找到规则图片: {rule_data['rule_id']}")
                        existing_rule.save()
                        updated_count += 1
                        logger.info(f"更新聚合规则: {rule_data['name']}")
                    else:
                        logger.info(f"规则已存在，跳过: {rule_data['name']}")
                        continue
                else:
                    image = self.get_rule_image(rule_data['rule_id'])
                    if image:
                        rule_data['image'] = image
                    else:
                        logger.warning(f"未找到规则图片: {rule_data['rule_id']}")
                    # 创建新规则
                    AggregationRules.objects.create(**rule_data)
                    created_count += 1
                    logger.info(f"创建聚合规则: {rule_data['name']}")

            except Exception as e:
                logger.error(f"处理规则失败 {rule_data.get('name', 'Unknown')}: {str(e)}")

        logger.info(f"聚合规则处理完成 - 创建: {created_count}, 更新: {updated_count}")
        return created_count, updated_count

    def get_rule_image(self, rule_id):
        image_path = f"{settings.BASE_DIR}/{self.base_path}/{rule_id}.png"
        try:
            base64_data = image_to_base64(image_path=image_path, output_format="png")
        except Exception as e:
            logger.error(f"获取规则图片失败 {rule_id}: {str(e)}")
            return
        return base64_data
