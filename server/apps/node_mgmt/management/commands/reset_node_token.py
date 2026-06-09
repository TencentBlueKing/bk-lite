from django.core.management import BaseCommand, CommandError

from apps.core.logger import node_logger as logger
from apps.node_mgmt.models import Node
from apps.node_mgmt.utils.token_auth import generate_node_token


class Command(BaseCommand):
    help = "根据已有 node_id 重置节点 token"

    def add_arguments(self, parser):
        parser.add_argument(
            "--node-id",
            type=str,
            required=True,
            help="需要重置 token 的节点ID",
        )
        parser.add_argument(
            "--ip",
            type=str,
            default=None,
            help="写入 token payload 的 IP；不传时优先使用节点表中的 IP",
        )
        parser.add_argument(
            "--user",
            type=str,
            default="system",
            help="写入 token payload 的用户标识",
        )

    def handle(self, *args, **options):
        node_id = (options["node_id"] or "").strip()
        if not node_id:
            raise CommandError("--node-id 不能为空")

        ip = options["ip"]
        if ip is None:
            ip = Node.objects.filter(id=node_id).values_list("ip", flat=True).first() or ""
        else:
            ip = ip.strip()

        user = (options["user"] or "system").strip() or "system"

        logger.info("开始重置节点 token，node_id=%s, ip=%s, user=%s", node_id, ip, user)
        token = generate_node_token(node_id, ip, user)
        logger.info("节点 token 重置完成，node_id=%s", node_id)

        self.stdout.write(f"node_id: {node_id}")
        self.stdout.write(f"token: {token}")
