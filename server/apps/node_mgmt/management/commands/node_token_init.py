import uuid

from django.core.management import BaseCommand
from apps.core.logger import node_logger as logger
from apps.node_mgmt.utils.token_auth import generate_node_token


class Command(BaseCommand):
    help = "node token 初始化"

    def add_arguments(self, parser):
        parser.add_argument(
            "--ip",
            type=str,
            help="ip地址",
            default="",
        )
        parser.add_argument(
            "--user",
            type=str,
            help="用户名",
            default="admin",
        )

    def handle(self, *args, **options):
        logger.info("node token 初始化开始！")
        node_id = uuid.uuid1().hex
        token = generate_node_token(node_id, options["ip"], options["user"])
        logger.info(f"node_id: {node_id}, token: {token}")
        logger.info("node token 初始化完成！")
