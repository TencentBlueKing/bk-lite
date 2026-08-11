from django.core.management.base import BaseCommand, CommandError

from apps.opspilot.services.wiki.directory_readiness_service import audit_wiki_directory_readiness


class Command(BaseCommand):
    help = "只读审计 Wiki 知识库目录治理就绪度（不写库）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--knowledge-base-ids",
            nargs="*",
            type=int,
            default=None,
            dest="knowledge_base_ids",
            help="仅审计指定知识库 ID；缺省审计全部",
        )
        parser.add_argument(
            "--compact",
            action="store_true",
            help="压缩输出，只打印阻塞问题代码",
        )
        parser.add_argument(
            "--enable-check",
            action="store_true",
            help="按 enable 路径做严格检查",
        )

    def handle(self, *args, **options):
        knowledge_base_ids = options.get("knowledge_base_ids")
        report = audit_wiki_directory_readiness(
            knowledge_base_ids=knowledge_base_ids,
            enable_check=bool(options.get("enable_check")),
        )
        payload = report.to_dict()
        if options.get("compact"):
            for item in payload.get("knowledge_bases") or []:
                kb_id = item.get("knowledge_base_id")
                codes = []
                for issue in item.get("issues") or []:
                    if not issue.get("blocking"):
                        continue
                    code = issue.get("code") or "unknown"
                    entity_id = issue.get("entity_id")
                    if entity_id is not None and entity_id != "":
                        codes.append(f"{code}#{entity_id}")
                    else:
                        codes.append(str(code))
                if codes:
                    self.stdout.write(f"kb={kb_id} " + ",".join(codes))
                else:
                    self.stdout.write(f"kb={kb_id} ready")
            if payload.get("missing_knowledge_base_ids"):
                self.stdout.write("missing=" + ",".join(str(item) for item in payload["missing_knowledge_base_ids"]))
        else:
            import json

            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))

        if not report.ready:
            failed = [str(item.get("knowledge_base_id")) for item in payload.get("knowledge_bases") or [] if not item.get("ready")]
            failed.extend(str(item) for item in payload.get("missing_knowledge_base_ids") or [])
            raise CommandError(f"failed_kb_ids={','.join(failed)}")
