# 历史收敛合并节点。
# 因 0025_merge 的依赖被收敛到公共祖先 0023（以兼容“两个 0024”旧版库与
# “单个 0024”新版库两类迁移历史），0024_alter_changerecord_scenario、
# 0024_cmdbfileobject、0024_custom_reporting 以及 0026 形成多个叶子节点。
# 本空操作迁移将它们重新汇聚为单一 head，使后续 makemigrations / migrate 不再
# 出现 multiple leaf nodes 告警。三类库（旧版 / 新版 / 全新）应用本节点均为无操作。
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0024_alter_changerecord_scenario'),
        ('cmdb', '0024_cmdbfileobject'),
        ('cmdb', '0024_custom_reporting'),
        ('cmdb', '0026_collectmodels_topology_snapshot'),
    ]

    operations = [
    ]
