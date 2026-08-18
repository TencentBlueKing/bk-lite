from django.core.management.base import BaseCommand

from apps.operation_analysis.models.models import Directory


def find_directory_cycles(parent_by_id):
    """Return canonical node-id tuples for every cycle in a parent mapping."""
    cycles = set()
    resolved = set()

    for start_id in parent_by_id:
        if start_id in resolved:
            continue

        path = []
        path_indexes = {}
        current_id = start_id
        while current_id is not None and current_id in parent_by_id and current_id not in resolved:
            if current_id in path_indexes:
                cycle = tuple(sorted(path[path_indexes[current_id] :]))
                cycles.add(cycle)
                break
            path_indexes[current_id] = len(path)
            path.append(current_id)
            current_id = parent_by_id[current_id]
        resolved.update(path)

    return sorted(cycles)


class Command(BaseCommand):
    help = "只读检查运营分析目录的循环父链；不修改任何目录关系。"

    def handle(self, *args, **options):
        parent_by_id = dict(Directory.objects.order_by("id").values_list("id", "parent_id"))
        cycles = find_directory_cycles(parent_by_id)

        if not cycles:
            self.stdout.write(self.style.SUCCESS("未发现目录循环。"))
            return

        for cycle in cycles:
            self.stdout.write(self.style.WARNING("发现目录循环: " + " -> ".join(map(str, cycle))))
        self.stdout.write(self.style.WARNING(f"共发现 {len(cycles)} 个目录循环；请先备份并人工解除父关系后再复查。"))
