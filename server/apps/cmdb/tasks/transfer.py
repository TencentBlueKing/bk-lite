from celery import shared_task

from apps.cmdb.services.transfer_dispatch import TransferDispatch
from apps.cmdb.services.transfer_execution import TransferExecution
from apps.cmdb.services.transfer_files import TransferFiles
from apps.cmdb.services.transfer_maintenance import TransferMaintenance


def dispatch_transfer(task_id):
    TransferMaintenance.dispatch(task_id, lambda value: TransferDispatch.submit(value, send_transfer))


def send_transfer(task_id):
    # 不占用共享生产者池，不在一次发布里累积连接重试；失败由持久化补发负责。
    with execute_transfer.app.connection_for_write(
        connect_timeout=2, transport_options={"max_retries": 0, "socket_connect_timeout": 2, "socket_timeout": 2}
    ) as connection:
        execute_transfer.apply_async(args=[str(task_id)], connection=connection, retry=False, timeout=2, confirm_timeout=2)


# 使用现有 Worker 的默认队列；threads 池依靠数据库截止时间和执行令牌协作停止。
@shared_task(soft_time_limit=900, time_limit=960, max_retries=0, ignore_result=True)
def execute_transfer(task_id):
    TransferExecution.run(task_id)


@shared_task(ignore_result=True)
def maintain_transfers():
    TransferMaintenance.maintain(send_transfer)


@shared_task(ignore_result=True)
def cleanup_transfers():
    TransferMaintenance.cleanup(TransferFiles())
