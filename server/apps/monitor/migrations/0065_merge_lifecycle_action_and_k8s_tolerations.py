# Merge the alert-event lifecycle branch with the K8s DaemonSet tolerations branch.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0064_monitorevent_lifecycle_action"),
        ("monitor", "0064_monitorinstance_k8s_daemonset_tolerations"),
    ]

    operations = []
