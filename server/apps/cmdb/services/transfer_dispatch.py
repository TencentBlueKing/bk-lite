"""接纳后的快速投递提示；数据库任务记录与定时补发始终是持久化依据。"""

from threading import BoundedSemaphore, Thread

from apps.cmdb.services.transfer_maintenance import TransferMaintenance


class TransferDispatch:
    # 不维护内存等待队列。Broker 卡住时最多占两个线程，其余由数据库补发接管。
    _slots = BoundedSemaphore(2)

    @classmethod
    def submit(cls, task_id, send):
        if not cls._slots.acquire(blocking=False):
            return

        def publish():
            try:
                TransferMaintenance.publish(task_id, send)
            finally:
                cls._slots.release()

        try:
            Thread(target=publish, name="cmdb-transfer-publish", daemon=True).start()
        except Exception:
            cls._slots.release()
            raise  # dispatch 边界记录失败，数据库补发不受影响。
