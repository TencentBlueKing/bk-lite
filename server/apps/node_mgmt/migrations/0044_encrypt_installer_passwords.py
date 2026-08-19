from django.db import migrations

from apps.core.utils.crypto.aes_crypto import AESCryptor


INSTALLER_PASSWORD_KEY = "NATS_INSTALLER_PASSWORD"
SECRET_TYPE = "secret"
BATCH_SIZE = 100


def encrypt_installer_passwords(apps, schema_editor):
    """幂等加密存量安装密码；旧版本已支持读取 secret，代码回滚无需解密。"""
    sidecar_env = apps.get_model("node_mgmt", "SidecarEnv")
    database_alias = schema_editor.connection.alias
    rows = (
        sidecar_env.objects.using(database_alias)
        .filter(key=INSTALLER_PASSWORD_KEY)
        .exclude(type=SECRET_TYPE)
        .exclude(value="")
        .order_by("pk")
        .iterator(chunk_size=BATCH_SIZE)
    )
    cryptor = AESCryptor()
    for row in rows:
        sidecar_env.objects.using(database_alias).filter(pk=row.pk).update(
            value=cryptor.encode(row.value),
            type=SECRET_TYPE,
        )


class Migration(migrations.Migration):
    dependencies = [("node_mgmt", "0043_alter_controllertasknode_password")]

    operations = [
        migrations.RunPython(encrypt_installer_passwords, migrations.RunPython.noop),
    ]
