"""opspilot-core 切片: utils/celery_task_utils 真实 DB 测试。

无外部边界 mock —— 直接用真实 django_celery_beat 的 CrontabSchedule/PeriodicTask
ORM 与真实 schedule_utils 生成逻辑。断言批量创建/删除的真实行数、任务命名规则、
crontab 复用（去重）、kwargs 序列化、无效配置跳过、_crontab_dict_to_key 纯函数。
"""

import pydantic.root_model  # noqa

import json

import pytest

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

CrontabSchedule = PeriodicTask = None


@pytest.fixture(scope="module", autouse=True)
def _load_beat_models():
    global CrontabSchedule, PeriodicTask
    from django_celery_beat.models import CrontabSchedule as CS, PeriodicTask as PT

    CrontabSchedule = CS
    PeriodicTask = PT


@pytest.fixture(scope="module")
def celery_task_utils():
    from apps.opspilot.utils import celery_task_utils

    return celery_task_utils


def _celery_node(node_id, config):
    return {"id": node_id, "type": "celery", "data": {"config": config}}


class TestCrontabDictToKey:
    def test_key_is_hashable_tuple(self, celery_task_utils):
        d = {"minute": "0", "hour": "9", "day_of_week": "*", "day_of_month": "*", "month_of_year": "*"}
        key = celery_task_utils._crontab_dict_to_key(d)
        assert key == ("0", "9", "*", "*", "*")
        # 可作为 dict 键
        assert {key: 1}[key] == 1


class TestCreateCeleryTask:
    def test_daily_multi_time_creates_one_task_per_time(self, celery_task_utils):
        work_data = {"nodes": [_celery_node("n1", {
            "frequency": "daily",
            "time": ["09:00", "18:30"],
            "message": "早晚提醒",
        })]}
        celery_task_utils.create_celery_task(101, work_data)

        tasks = PeriodicTask.objects.filter(name__startswith="chat_flow_celery_task_101_")
        assert tasks.count() == 2
        names = sorted(t.name for t in tasks)
        assert names == [
            "chat_flow_celery_task_101_n1_0",
            "chat_flow_celery_task_101_n1_1",
        ]
        # task 路径与 kwargs 正确序列化
        t0 = tasks.get(name="chat_flow_celery_task_101_n1_0")
        assert t0.task == "apps.opspilot.tasks.chat_flow_celery_task"
        assert json.loads(t0.kwargs) == {"bot_id": 101, "node_id": "n1", "message": "早晚提醒"}
        assert t0.enabled is True
        # crontab 绑定: 09:00 -> minute=0 hour=9
        assert (t0.crontab.minute, t0.crontab.hour) == ("0", "9")

    def test_identical_crontab_reused_across_tasks(self, celery_task_utils):
        # 两个节点同一时间，应复用同一 CrontabSchedule
        work_data = {"nodes": [
            _celery_node("a", {"frequency": "daily", "time": ["10:00"], "message": "m"}),
            _celery_node("b", {"frequency": "daily", "time": ["10:00"], "message": "m"}),
        ]}
        before = CrontabSchedule.objects.count()
        celery_task_utils.create_celery_task(202, work_data)
        after = CrontabSchedule.objects.count()
        # 只新增一个 crontab（去重）
        assert after - before == 1
        assert PeriodicTask.objects.filter(name__startswith="chat_flow_celery_task_202_").count() == 2

    def test_weekly_crontab_fields(self, celery_task_utils):
        work_data = {"nodes": [_celery_node("w", {
            "frequency": "weekly",
            "time": ["08:15"],
            "weekdays": [1, 3, 5],
            "message": "周报",
        })]}
        celery_task_utils.create_celery_task(303, work_data)
        t = PeriodicTask.objects.get(name="chat_flow_celery_task_303_w_0")
        assert t.crontab.day_of_week == "1,3,5"
        assert (t.crontab.minute, t.crontab.hour) == ("15", "8")

    def test_node_without_frequency_skipped(self, celery_task_utils):
        work_data = {"nodes": [_celery_node("nf", {"message": "no freq"})]}
        celery_task_utils.create_celery_task(404, work_data)
        assert PeriodicTask.objects.filter(name__startswith="chat_flow_celery_task_404_").count() == 0

    def test_invalid_config_skipped_gracefully(self, celery_task_utils):
        # weekly 缺 weekdays -> 校验失败，跳过且不抛
        work_data = {"nodes": [_celery_node("bad", {
            "frequency": "weekly",
            "time": ["08:00"],
            "message": "x",
        })]}
        celery_task_utils.create_celery_task(505, work_data)
        assert PeriodicTask.objects.filter(name__startswith="chat_flow_celery_task_505_").count() == 0

    def test_non_celery_nodes_ignored(self, celery_task_utils):
        work_data = {"nodes": [
            {"id": "llm1", "type": "llm", "data": {"config": {}}},
            _celery_node("c", {"frequency": "daily", "time": ["12:00"], "message": "m"}),
        ]}
        celery_task_utils.create_celery_task(606, work_data)
        assert PeriodicTask.objects.filter(name__startswith="chat_flow_celery_task_606_").count() == 1


class TestDeleteCeleryTask:
    def test_create_then_delete_removes_only_that_bot(self, celery_task_utils):
        celery_task_utils.create_celery_task(701, {"nodes": [_celery_node("n", {"frequency": "daily", "time": ["09:00"], "message": "m"})]})
        celery_task_utils.create_celery_task(702, {"nodes": [_celery_node("n", {"frequency": "daily", "time": ["09:00"], "message": "m"})]})

        celery_task_utils.delete_celery_task(701)
        assert PeriodicTask.objects.filter(name__startswith="chat_flow_celery_task_701_").count() == 0
        # 其他 bot 的任务保留
        assert PeriodicTask.objects.filter(name__startswith="chat_flow_celery_task_702_").count() == 1

    def test_delete_nonexistent_is_noop(self, celery_task_utils):
        # 不存在的 bot 删除不抛异常
        celery_task_utils.delete_celery_task(999999)

    def test_create_is_idempotent_replaces_old(self, celery_task_utils):
        # 二次 create_celery_task 先删旧任务，避免重复
        cfg = {"nodes": [_celery_node("n", {"frequency": "daily", "time": ["09:00", "10:00"], "message": "m"})]}
        celery_task_utils.create_celery_task(808, cfg)
        celery_task_utils.create_celery_task(808, cfg)
        assert PeriodicTask.objects.filter(name__startswith="chat_flow_celery_task_808_").count() == 2
