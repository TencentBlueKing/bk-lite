from pyarrow.conftest import defaults

from apps.core.logger import playground_logger as logger

from django.core.management import BaseCommand

from apps.playground.models import PlayGroundCategory
from apps.playground.init_constant import CATEGORY_INIT_DATA

class Command(BaseCommand):
    help = "初始化分类"

    def handle(self, *args, **options):
        logger.info("开始初始化分类")
        try:
            for item in CATEGORY_INIT_DATA:
                if "name" not in item or not item["name"]:
                    logger.error("分类名称不能为空")
                    continue
                else:
                    _, created = PlayGroundCategory.objects.get_or_create(
                        name=item["name"],  # 只有name作为查询条件
                        defaults={  # 其他字段作为创建时的默认值
                            "description": item.get("description", ""),
                            "parent": item.get("parent", None),
                            "created_by": item.get("created_by", "system"),
                            "updated_by": item.get("updated_by", "system")
                        }
                    )
                    if created:
                        logger.info(f"初始化分类成功: {item['name']}")
                    else:
                        logger.info(f"分类已存在: {item['name']}")
        except Exception as e:
            logger.error(f"初始化分类失败: {e}")
