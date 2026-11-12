"""按应用重算 ci_context。

    python manage.py rebuild_ci_context
    python manage.py rebuild_ci_context --model-asst-id=application_run_host
"""

from django.core.management.base import BaseCommand, CommandError

from apps.cmdb.services.ci_context import APPLICATION_PAGE_SIZE, _roots_for_model_asst, rebuild_ci_context_bounded, recompute_application
from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_info, safe_log_value

PAGE_SIZE = APPLICATION_PAGE_SIZE


class Command(BaseCommand):
    help = "按应用全量重算 ci_context，或只重算使用指定关联的应用"

    def add_arguments(self, parser):
        parser.add_argument("--model-asst-id", default="", help="只重算使用该模型关联的应用")

    def handle(self, *args, **options):
        model_asst_id = str(options.get("model_asst_id") or "").strip()
        if model_asst_id:
            ok_count, fail_count = _rebuild_uuids(_application_uuids(_roots_for_model_asst(model_asst_id)))
        else:
            ok_count, fail_count = _rebuild_all()

        if fail_count:
            raise CommandError(f"ci_context rebuild failed recomputed={ok_count} failed={fail_count}")
        self.stdout.write(self.style.SUCCESS(f"ci_context rebuild finished recomputed={ok_count}"))


def _rebuild_all() -> tuple[int, int]:
    skip = 0
    ok_count = 0
    fail_count = 0
    while True:
        result = rebuild_ci_context_bounded(skip=skip, limit=PAGE_SIZE)
        ok_count += result["ok_count"]
        fail_count += result["fail_count"]
        if result["done"]:
            return ok_count, fail_count
        skip = result["next_skip"]


def _rebuild_uuids(inst_uuids) -> tuple[int, int]:
    ok_count = 0
    fail_count = 0
    for inst_uuid in inst_uuids:
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
    return ok_count, fail_count


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
