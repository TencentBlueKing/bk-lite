from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.mlops.models.dataset_release_execution import DatasetReleaseObjectCleanup, DatasetReleaseObjectCleanupCursor
from apps.mlops.tasks import base


class Command(BaseCommand):
    help = "重试清理数据集发布遗留对象，并保留删除失败的补偿意图"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=1000)
        parser.add_argument("--dry-run", action="store_true")

    @staticmethod
    def _candidate_ids(limit, *, dry_run):
        if dry_run:
            last_intent_id = DatasetReleaseObjectCleanupCursor.objects.filter(scope="global").values_list("last_intent_id", flat=True).first() or 0
            intent_ids = list(DatasetReleaseObjectCleanup.objects.filter(id__gt=last_intent_id).order_by("id").values_list("id", flat=True)[:limit])
            if intent_ids or not last_intent_id:
                return intent_ids
            return list(DatasetReleaseObjectCleanup.objects.order_by("id").values_list("id", flat=True)[:limit])

        with transaction.atomic():
            cursor, _ = DatasetReleaseObjectCleanupCursor.objects.get_or_create(scope="global")
            cursor = DatasetReleaseObjectCleanupCursor.objects.select_for_update().get(id=cursor.id)
            intent_ids = list(
                DatasetReleaseObjectCleanup.objects.filter(id__gt=cursor.last_intent_id).order_by("id").values_list("id", flat=True)[:limit]
            )
            if not intent_ids and cursor.last_intent_id:
                intent_ids = list(DatasetReleaseObjectCleanup.objects.order_by("id").values_list("id", flat=True)[:limit])
            if intent_ids:
                cursor.last_intent_id = intent_ids[-1]
                cursor.save(update_fields=["last_intent_id"])
            return intent_ids

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 1000:
            raise CommandError("--limit 必须在 1 到 1000 之间")

        intent_ids = self._candidate_ids(limit, dry_run=options["dry_run"])
        if not intent_ids:
            self.stdout.write("没有待清理的数据集发布对象")
            return
        if options["dry_run"]:
            for intent_id in intent_ids:
                action, object_path = base.inspect_dataset_release_object_cleanup(intent_id)
                self.stdout.write(f"dry-run intent_id={intent_id} action={action} path={object_path}")
            self.stdout.write(f"数据集发布对象补偿预检: candidates={len(intent_ids)}")
            return

        storage = base.MinioBackend(bucket_name="munchkin-public")
        cleaned = 0
        skipped = 0
        retained = 0
        for intent_id in intent_ids:
            claim = base.claim_dataset_release_object_cleanup(intent_id)
            if claim is None:
                skipped += 1
                self.stdout.write(f"skipped intent_id={intent_id}")
                continue
            cleaned_object = base.delete_stale_publish_object(
                storage,
                claim.object_path,
            )
            base.complete_dataset_release_object_cleanup(
                claim,
                cleaned=cleaned_object,
            )
            if cleaned_object:
                cleaned += 1
                self.stdout.write(f"cleaned intent_id={intent_id}")
            else:
                retained += 1
                self.stdout.write(f"retained intent_id={intent_id}")

        self.stdout.write(f"数据集发布对象补偿完成: cleaned={cleaned} " f"skipped_active={skipped} retained={retained}")
