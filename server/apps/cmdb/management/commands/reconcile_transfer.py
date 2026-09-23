from django.core.management.base import BaseCommand, CommandError

from apps.cmdb.services.transfer_service import TransferService


class Command(BaseCommand):
    help = "确认旧 Worker 已停止、核对操作账本与图库后，解除导入导出中断占用；不会重放任务"

    def add_arguments(self, parser):
        parser.add_argument("task_id")
        parser.add_argument("--verified-stopped", action="store_true")
        parser.add_argument("--note", required=True)

    def handle(self, *args, **options):
        if not options["verified_stopped"]:
            raise CommandError("请先核实 Worker 已退出和写入副作用，再传 --verified-stopped")
        if len(options["note"]) > 300:
            raise CommandError("核对备注最多 300 字，不得填写凭据或实例内容")
        from apps.cmdb.models.transfer_task import CmdbTransferTask

        task = CmdbTransferTask.objects.get(pk=options["task_id"])
        summary = dict(task.summary, reconciliation_note=options["note"])
        if not TransferService.reconcile_interrupted(task.pk, verified_stopped=True, summary=summary):
            raise CommandError("任务不处于待核对状态")
        self.stdout.write(self.style.SUCCESS("已解除占用；任务未重跑"))
