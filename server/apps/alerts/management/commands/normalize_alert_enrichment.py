from django.core.management.base import BaseCommand

from apps.alerts.enrichment.merge import normalize_enrichment_document
from apps.alerts.models.models import Alert, Event


class Command(BaseCommand):
    help = "分页、幂等地把 Event/Alert 历史 enrichment namespace 数组转换为稳定对象"

    def add_arguments(self, parser):
        parser.add_argument("--model", choices=("event", "alert", "all"), default="all")
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--start-after-id", type=int, default=0)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        selected = options["model"]
        models = []
        if selected in {"event", "all"}:
            models.append(Event)
        if selected in {"alert", "all"}:
            models.append(Alert)

        total_scanned = 0
        total_updated = 0
        for model in models:
            scanned, updated = self._normalize_model(
                model,
                batch_size=max(1, options["batch_size"]),
                start_after_id=max(0, options["start_after_id"]),
                dry_run=options["dry_run"],
            )
            total_scanned += scanned
            total_updated += updated
        self.stdout.write(self.style.SUCCESS(f"scanned={total_scanned}, updated={total_updated}, dry_run={options['dry_run']}"))

    @staticmethod
    def _normalize_model(model, *, batch_size: int, start_after_id: int, dry_run: bool):
        cursor = start_after_id
        scanned = 0
        updated = 0
        while True:
            batch = list(model.objects.filter(pk__gt=cursor).only("id", "enrichment").order_by("pk")[:batch_size])
            if not batch:
                break
            changed_objects = []
            for instance in batch:
                scanned += 1
                normalized, changed = normalize_enrichment_document(instance.enrichment)
                if changed:
                    instance.enrichment = normalized
                    changed_objects.append(instance)
            if changed_objects:
                updated += len(changed_objects)
                if not dry_run:
                    model.objects.bulk_update(changed_objects, ["enrichment"], batch_size=batch_size)
            cursor = batch[-1].pk
        return scanned, updated
