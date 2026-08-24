from django.core.management.base import BaseCommand, CommandError

from apps.mlops.models.dataset_release_execution import DatasetReleaseObjectCleanup
from apps.mlops.tasks import base


class Command(BaseCommand):
    help = "重试清理数据集发布遗留对象，并保留删除失败的补偿意图"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=1000)

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit 必须大于 0")

        intent_ids = list(DatasetReleaseObjectCleanup.objects.order_by("id").values_list("id", flat=True)[:limit])
        if not intent_ids:
            self.stdout.write("没有待清理的数据集发布对象")
            return

        storage = base.MinioBackend(bucket_name="munchkin-public")
        cleaned = 0
        skipped = 0
        retained = 0
        for intent_id in intent_ids:
            claim = base.claim_dataset_release_object_cleanup(intent_id)
            if claim is None:
                skipped += 1
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
            else:
                retained += 1

        self.stdout.write(f"数据集发布对象补偿完成: cleaned={cleaned} " f"skipped_active={skipped} retained={retained}")
