"""维护 OpenAPI 网关的 base_url 允许清单（DB 侧）。

改动一个拉取周期内生效，无需重建 server 容器。环境变量
OPENAPI_BASEURL_ALLOWLIST 里的存量条目只读，本命令不改动它们。
"""

from django.core.management.base import BaseCommand, CommandError

from apps.core.openapi.allowlist import AllowlistError, add_host, db_hosts, env_hosts, remove_host


class Command(BaseCommand):
    help = "查看 / 增删 OpenAPI 网关 base_url 允许清单（DB 侧）"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["list", "add", "remove"])
        parser.add_argument("host", nargs="?", help="主机名或 IP；前导点表示按点边界的后缀匹配")

    def handle(self, *args, **options):
        action = options["action"]
        host = options.get("host")

        if action == "list":
            self._render_list()
            return

        if not host:
            raise CommandError(f"{action} 需要指定 host")
        try:
            hosts = add_host(host) if action == "add" else remove_host(host)
        except AllowlistError as exc:
            raise CommandError(str(exc)) from exc
        verb = "已加入" if action == "add" else "已移除"
        self.stdout.write(f"{verb} {host}，DB 侧当前 {len(hosts)} 项：{', '.join(hosts) or '(空)'}")
        self.stdout.write("下一个拉取周期内生效，无需重建 server。")

    def _render_list(self):
        from_env = env_hosts()
        from_db = db_hosts()
        self.stdout.write(f"DB  ({len(from_db)} 项，本命令可改)：{', '.join(from_db) or '(空)'}")
        self.stdout.write(f"ENV ({len(from_env)} 项，改动需重建 server)：{', '.join(from_env) or '(空)'}")
        if not from_env and not from_db:
            self.stdout.write("清单为空，所有外部服务条目都会被跳过（fail-closed）。")
