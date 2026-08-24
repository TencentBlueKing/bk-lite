from django.db import migrations, transaction

from apps.core.utils.crypto.aes_crypto import AESCryptor


INSTALLER_PASSWORD_KEY = "NATS_INSTALLER_PASSWORD"
SECRET_TYPE = "secret"
BATCH_SIZE = 100


def encrypt_installer_passwords(apps, schema_editor):
    """幂等加密存量安装密码；旧版本已支持读取 secret，代码回滚无需解密。"""
    sidecar_env = apps.get_model("node_mgmt", "SidecarEnv")
    database_alias = schema_editor.connection.alias
    cryptor = AESCryptor()
    last_pk = 0
    while True:
        with transaction.atomic(using=database_alias):
            rows = list(
                sidecar_env.objects.using(database_alias)
                .select_for_update()
                .filter(key=INSTALLER_PASSWORD_KEY, pk__gt=last_pk)
                .exclude(type=SECRET_TYPE)
                .exclude(value="")
                .order_by("pk")[:BATCH_SIZE]
            )
            if not rows:
                return
            for row in rows:
                row.value = cryptor.encode(row.value)
                row.type = SECRET_TYPE
                row.save(update_fields=["value", "type"], using=database_alias)
            last_pk = rows[-1].pk


class Migration(migrations.Migration):
    atomic = False

    dependencies = [("node_mgmt", "0043_alter_controllertasknode_password")]

    operations = [
        migrations.RunPython(encrypt_installer_passwords, migrations.RunPython.noop),
    ]
