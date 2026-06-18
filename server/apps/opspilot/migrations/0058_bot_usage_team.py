from django.db import migrations, models


def backfill_usage_team(apps, schema_editor):
    """存量 bot 的使用组织初始化为管理组织。

    新增字段后,execute_chat_flow 统一按 usage_team 鉴权。若不回填,存量 bot 的
    usage_team 为空,会导致原本能对话的管理组织成员全部被挡(重大回归)。回填
    usage_team = team 后,存量 bot 的对话行为与改动前完全一致。
    """
    Bot = apps.get_model("opspilot", "Bot")
    to_update = []
    for bot in Bot.objects.all().iterator():
        if not bot.usage_team:
            bot.usage_team = list(bot.team or [])
            to_update.append(bot)
    if to_update:
        Bot.objects.bulk_update(to_update, ["usage_team"], batch_size=500)


def noop_reverse(apps, schema_editor):
    # 反向迁移随 RemoveField 一并丢弃数据,无需额外处理。
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("opspilot", "0057_workflowtaskresult_is_test"),
    ]

    operations = [
        migrations.AddField(
            model_name="bot",
            name="usage_team",
            field=models.JSONField(default=list, verbose_name="使用组织"),
        ),
        migrations.RunPython(backfill_usage_team, noop_reverse),
    ]
