"""按应用重算 ci_context。

    python manage.py rebuild_ci_context
    python manage.py rebuild_ci_context --model-asst-id=application_run_host
"""

from django.core.management.base import BaseCommand, CommandError

from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.ci_context import _roots_for_model_asst, recompute_application
from apps.cmdb.services.ci_context_policy import APPLICATION_MODEL
from apps.core.logger import cmdb_logger as logger, safe_exception_info, safe_log_value

PAGE_SIZE = 200


class Command(BaseCommand):
    help = "按应用全量重算 ci_context，或只重算使用指定关联的应用"

    def add_arguments(self, parser):
        parser.add_argument("--model-asst-id", default="", help="只重算使用该模型关联的应用")

    def handle(self, *args, **options):
        model_asst_id = str(options.get("model_asst_id") or "").strip()
        if model_asst_id:
            application_uuids = _application_uuids(_roots_for_model_asst(model_asst_id))
        else:
            application_uuids = _page_application_uuids()

        ok_count = 0
        fail_count = 0
        for inst_uuid in application_uuids:
            try:
                recompute_application(inst_uuid)
            except Exception as exc:
                fail_count += 1
                logger.exception(
                    "event=ci_context_rebuild_failed inst_uuid=%s failed_stage=%s error_type=%s",
                    safe_log_value(inst_uuid),
                    "recompute_application",
                    type(exc).__name__,
                    exc_info=safe_exception_info(exc),
                )
                continue
            ok_count += 1

        if fail_count:
            raise CommandError(f"ci_context rebuild failed recomputed={ok_count} failed={fail_count}")
        self.stdout.write(self.style.SUCCESS(f"ci_context rebuild finished recomputed={ok_count}"))


def _page_application_uuids() -> list:
    found = []
    skip = 0
    with GraphClient() as client:
        while True:
            rows, _count = client.query_entity(
                INSTANCE,
                [{"field": "model_id", "type": "str=", "value": APPLICATION_MODEL}],
                page={"skip": skip, "limit": PAGE_SIZE},
                fields=["inst_uuid"],
                include_count=False,
            )
            batch = list(rows or [])
            if not batch:
                break
            found.extend(_application_uuids(row.get("inst_uuid") for row in batch if isinstance(row, dict)))
            if len(batch) < PAGE_SIZE:
                break
            skip += PAGE_SIZE
    return _application_uuids(found)


def _application_uuids(values) -> list:
    found = []
    seen = set()
    for value in values or []:
        inst_uuid = str(value or "").strip()
        if not inst_uuid or inst_uuid in seen:
            continue
        seen.add(inst_uuid)
        found.append(inst_uuid)
    return found
