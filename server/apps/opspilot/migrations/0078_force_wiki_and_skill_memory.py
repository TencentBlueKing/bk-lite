import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q

_PLATFORM_CHANNEL_TYPES = ("platform", "web_chat", "embedded_chat")


def backfill_memory_owner_user_id(apps, schema_editor):
    Memory = apps.get_model("opspilot", "Memory")
    SkillConversation = apps.get_model("opspilot", "SkillConversation")
    SkillChannel = apps.get_model("opspilot", "SkillChannel")
    User = apps.get_model("system_mgmt", "User")

    missing = list(User.objects.filter(Q(user_id__isnull=True) | Q(user_id="")).only("id", "user_id"))
    for user in missing:
        user.user_id = str(uuid.uuid4())
    if missing:
        User.objects.bulk_update(missing, ["user_id"], batch_size=500)

    users = User.objects.exclude(user_id__isnull=True).exclude(user_id="").only("username", "domain", "user_id")
    platform_channel_ids = list(SkillChannel.objects.filter(channel_type__in=_PLATFORM_CHANNEL_TYPES).values_list("id", flat=True))
    for user in users.iterator(chunk_size=500):
        Memory.objects.filter(
            organization_id__isnull=True,
            owner_user_id__isnull=True,
            owner_username=user.username,
            owner_domain=user.domain or "",
        ).update(owner_user_id=user.user_id)
        if not platform_channel_ids:
            continue
        candidates = [user.username]
        if user.domain:
            candidates.append(f"{user.username}@{user.domain}")
        SkillConversation.objects.filter(channel_id__in=platform_channel_ids, external_user_id__in=candidates).update(external_user_id=user.user_id)


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0077_alter_llmskill_show_think"),
        ("system_mgmt", "0039_user_user_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmskill",
            name="force_wiki_grounded",
            field=models.BooleanField(default=False, verbose_name="强制知识库回答"),
        ),
        migrations.AddField(
            model_name="llmskill",
            name="memory_space",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="llm_skills",
                to="opspilot.memoryspace",
                verbose_name="记忆体",
            ),
        ),
        migrations.AddField(
            model_name="llmskill",
            name="memory_write_rounds",
            field=models.IntegerField(default=10, verbose_name="记忆写入轮数"),
        ),
        migrations.AddField(
            model_name="skillconversation",
            name="memory_written_message_id",
            field=models.BigIntegerField(default=0, verbose_name="已写入记忆的最后消息ID"),
        ),
        migrations.AddField(
            model_name="memoryspace",
            name="is_builtin",
            field=models.BooleanField(db_index=True, default=False, verbose_name="是否内置"),
        ),
        migrations.AddConstraint(
            model_name="memoryspace",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_builtin=True),
                fields=("is_builtin",),
                name="uniq_builtin_memory_space",
            ),
        ),
        migrations.AddField(
            model_name="memory",
            name="owner_user_id",
            field=models.CharField(blank=True, db_index=True, max_length=36, null=True, verbose_name="系统用户UUID"),
        ),
        migrations.RunPython(backfill_memory_owner_user_id, migrations.RunPython.noop),
    ]
