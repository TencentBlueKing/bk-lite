# Beat 遇到未来的上次运行时间时按当前时间续算

Status: implemented

## 现象

告警分派后的周期催办只发出第一次分派通知，后续到期催办不再发送。

现场样本：

- 告警 `ALERT-96944AD9D880461F888F23CBFDF55A0A`，级别 `0`，状态待响应。
- 提醒任务处于启用，`reminder_count=0`，频率 10 分钟，`next_reminder_time` 已是 `2026-11-17 02:58:14Z`。当时数据库时间是 `2026-11-18`。
- 周期任务 `check_and_send_reminders` 的 crontab 为每分钟、时区 UTC，`enabled=true`，`total_run_count=12961`。
- 该任务的 `last_run_at` 为 `2027-04-24 19:14:00.212994Z`。

手工调用 `ReminderService.check_and_process_reminders()` 可以发出积压催办。提醒行、渠道和扫描条件本身是通的。

## 产生原因

Celery 5.4.0 的 crontab 用 `last_run_at` 锚下一次触发，不用当前时间。`execute_this_hour` 还要求候选时刻与当前时间是同一天。`last_run_at` 落在 `2027-04-24 19:14`、当前时间是 `2026-11-18 09:00:45Z` 时，同一天分支被跳过；分钟和小时都是 `*`，下一次被算到未来那天的 `20:00`。`is_due=false`，等待约 `13604355` 秒。Beat 只在 `is_due` 时投递，所以 `check_and_send_reminders` 不会运行，到期催办不会被扫描。

`last_run_at` 由 django-celery-beat 2.6.0 的 `ModelEntry.__next__` 在任务执行后写成当时的进程时间。样本里同一天有多条不同整点，说明写入时 Beat 进程的日历停在 `2027-04-24`。本次不追查是哪台机器写下这个时间。

已排除的路径：

- Vastbase 的 naive 时间转换只按会话时区平移，通常是 0 或 8 小时，不能把 `2026-11` 写成 `2027-04`。库内 `NOW()` 仍在 2026，也不是整库读偏移。
- 催办扫描使用 `values_list("alert_id")` 再按主键加锁，历史的 `values_list("id")` 字段错误已经不在这条链路上。
- `max_count=0` 表示不限次数。频率变更只重算仍在未来的 `next_reminder_time`，已经过期的时间保持过期，会被扫描到。
- 分派成功当时只发 `scene=assignment`。周期催办是另一条 `scene=reminder`，由每分钟的 Beat 任务驱动。

## 修复方案

新增 `FutureLastRunDatabaseScheduler`，生产 Beat 的设置和 Supervisor 命令都指向它。生产命令写死了 `--scheduler`，只改 `CELERY_BEAT_SCHEDULER` 不够。

启用任务的 `last_run_at` 比 `_default_now()` 超前超过 60 秒时，本进程内先把它当成刚刚跑过，打一条 WARNING，再走原来的 `is_due`。数据库原值留到任务真正执行，`__next__` 再写成当时的当前时间。60 秒及以内保持原行为。过去的 `last_run_at` 不改写。

日志模板是 `event=celery_beat_future_last_run task=%s last_run_at=%s now=%s`，使用 `celery_logger`，不带 traceback。

恢复后的行为：

- 每分钟任务在 60 秒内重新到期。
- 按小时、按天的任务从当前时间起等自己的下一个 cron 槽，不会在恢复瞬间全部执行。
- 催办扫描恢复后的第一轮会发出当时所有已到期、仍待响应的催办。

部署需要重启 Beat。已卡住的行不需要先把 `last_run_at` 改成空。

## 测试结果

本地 sqlite，当前时间冻结在现场的 `2026-11-18 09:00:45Z`，`last_run_at` 使用现场的 `2027-04-24 19:14:00.212994Z`。

`server/apps/core/tests/test_beat_field_defect_compare.py` 对照旧调度与新调度：

| 调度 | 现场时刻 | 再过 61 秒 |
|---|---|---|
| 原 `ModelEntry` | `is_due=false`，还要等 `13604355` 秒 | `is_due=false`，还要等 `13604294` 秒 |
| 修复后的调度 | `is_due=false`，下次 `15` 秒 | `is_due=true` |

61 秒内不调用扫描，催办次数保持 0。放行后扫描结果为 `processed=1, success=1`，`reminder_count` 变为 1。回归断言锁定的是旧调度等待仍大于 `13600000` 秒、新调度下次不超过 60 秒，以及放行后的发送结果。

同一次清理后的复跑通过，并打出：

```text
event=celery_beat_future_last_run task=check_and_send_reminders last_run_at=2027-04-24T19:14:00.212994+00:00 now=2026-11-18T09:00:45+00:00
```

其余回归：

- `test_beat_future_last_run.py`：设置和 Entry 指向新调度；未来时间在 61 秒后到期，警告只打一次且数据库要等 `save()` 才改成当前时间；正好超前 60 秒不改写、不打日志；90 秒前的 `last_run_at` 仍然到期且保持原值。
- `test_reminder_beat_future_last_run.py`：同一告警在冻结时刻不发；61 秒后 `scene=reminder`，幂等键 `reminder:{pk}:1`，两个企微渠道都进入 outbox。
- `test_celery_runtime_pure.py`：Supervisor 的 beat 命令带上新调度器，不再写死 `django_celery_beat.schedulers.DatabaseScheduler`。

2026-11-19 在 sqlite 上复跑上述 7 条，全部通过。
