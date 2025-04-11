# Generated by Django 4.2.7 on 2025-04-11 07:27

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='CloudRegion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated Time')),
                ('created_by', models.CharField(default='', max_length=32, verbose_name='Creator')),
                ('updated_by', models.CharField(default='', max_length=32, verbose_name='Updater')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='云区域名称')),
                ('introduction', models.TextField(blank=True, verbose_name='云区域介绍')),
            ],
            options={
                'verbose_name': '云区域',
                'verbose_name_plural': '云区域',
            },
        ),
        migrations.CreateModel(
            name='Collector',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated Time')),
                ('created_by', models.CharField(default='', max_length=32, verbose_name='Creator')),
                ('updated_by', models.CharField(default='', max_length=32, verbose_name='Updater')),
                ('id', models.CharField(max_length=100, primary_key=True, serialize=False, verbose_name='采集器ID')),
                ('name', models.CharField(max_length=100, verbose_name='采集器名称')),
                ('service_type', models.CharField(choices=[('exec', '执行任务'), ('svc', '服务')], max_length=100, verbose_name='服务类型')),
                ('node_operating_system', models.CharField(choices=[('linux', 'Linux'), ('windows', 'Windows')], max_length=50, verbose_name='节点操作系统类型')),
                ('executable_path', models.CharField(max_length=200, verbose_name='可执行文件路径')),
                ('execute_parameters', models.CharField(max_length=200, verbose_name='执行参数')),
                ('validation_parameters', models.CharField(blank=True, max_length=200, null=True, verbose_name='验证参数')),
                ('default_template', models.TextField(blank=True, null=True, verbose_name='默认模板')),
                ('introduction', models.TextField(blank=True, verbose_name='采集器介绍')),
                ('icon', models.CharField(default='', max_length=100, verbose_name='图标key')),
            ],
            options={
                'verbose_name': '采集器信息',
                'verbose_name_plural': '采集器信息',
                'unique_together': {('node_operating_system', 'name')},
            },
        ),
        migrations.CreateModel(
            name='CollectorTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated Time')),
                ('created_by', models.CharField(default='', max_length=32, verbose_name='Creator')),
                ('updated_by', models.CharField(default='', max_length=32, verbose_name='Updater')),
                ('type', models.CharField(max_length=100, verbose_name='任务类型')),
                ('package_version_id', models.IntegerField(default=0, verbose_name='采集器版本')),
                ('status', models.CharField(max_length=100, verbose_name='任务状态')),
            ],
            options={
                'verbose_name': '采集器任务',
                'verbose_name_plural': '采集器任务',
            },
        ),
        migrations.CreateModel(
            name='ControllerTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated Time')),
                ('created_by', models.CharField(default='', max_length=32, verbose_name='Creator')),
                ('updated_by', models.CharField(default='', max_length=32, verbose_name='Updater')),
                ('type', models.CharField(max_length=100, verbose_name='任务类型')),
                ('status', models.CharField(max_length=100, verbose_name='任务状态')),
                ('work_node', models.CharField(blank=True, max_length=100, verbose_name='工作节点')),
                ('package_version_id', models.IntegerField(default=0, verbose_name='控制器版本')),
                ('cloud_region', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='node_mgmt.cloudregion', verbose_name='云区域')),
            ],
            options={
                'verbose_name': '控制器任务',
                'verbose_name_plural': '控制器任务',
            },
        ),
        migrations.CreateModel(
            name='Node',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated Time')),
                ('created_by', models.CharField(default='', max_length=32, verbose_name='Creator')),
                ('updated_by', models.CharField(default='', max_length=32, verbose_name='Updater')),
                ('id', models.CharField(max_length=100, primary_key=True, serialize=False, verbose_name='节点ID')),
                ('name', models.CharField(max_length=100, verbose_name='节点名称')),
                ('ip', models.CharField(max_length=30, verbose_name='IP地址')),
                ('operating_system', models.CharField(choices=[('linux', 'Linux'), ('windows', 'Windows')], max_length=50, verbose_name='操作系统类型')),
                ('collector_configuration_directory', models.CharField(max_length=200, verbose_name='采集器配置目录')),
                ('metrics', models.JSONField(default=dict, verbose_name='指标')),
                ('status', models.JSONField(default=dict, verbose_name='状态')),
                ('tags', models.JSONField(default=list, verbose_name='标签')),
                ('log_file_list', models.JSONField(default=list, verbose_name='日志文件列表')),
                ('cloud_region', models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='node_mgmt.cloudregion', verbose_name='云区域')),
            ],
            options={
                'verbose_name': '节点信息',
                'verbose_name_plural': '节点信息',
            },
        ),
        migrations.CreateModel(
            name='SidecarApiToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated Time')),
                ('created_by', models.CharField(default='', max_length=32, verbose_name='Creator')),
                ('updated_by', models.CharField(default='', max_length=32, verbose_name='Updater')),
                ('token', models.CharField(max_length=100, verbose_name='Token')),
            ],
            options={
                'verbose_name': 'Sidecar API Token',
                'verbose_name_plural': 'Sidecar API Token',
            },
        ),
        migrations.CreateModel(
            name='PackageVersion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated Time')),
                ('created_by', models.CharField(default='', max_length=32, verbose_name='Creator')),
                ('updated_by', models.CharField(default='', max_length=32, verbose_name='Updater')),
                ('type', models.CharField(db_index=True, max_length=100, verbose_name='包类型(控制器/采集器)')),
                ('os', models.CharField(db_index=True, max_length=20, verbose_name='操作系统')),
                ('object', models.CharField(db_index=True, max_length=100, verbose_name='包对象')),
                ('version', models.CharField(max_length=100, verbose_name='包版本号')),
                ('name', models.CharField(max_length=100, verbose_name='包名称')),
                ('description', models.TextField(blank=True, verbose_name='包版本描述')),
            ],
            options={
                'verbose_name': '包版本信息',
                'verbose_name_plural': '包版本信息',
                'unique_together': {('os', 'object', 'version')},
            },
        ),
        migrations.CreateModel(
            name='ControllerTaskNode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip', models.CharField(max_length=100, verbose_name='IP地址')),
                ('os', models.CharField(max_length=100, verbose_name='操作系统')),
                ('organizations', models.JSONField(default=list, verbose_name='所属组织')),
                ('port', models.IntegerField(verbose_name='端口')),
                ('username', models.CharField(max_length=100, verbose_name='用户名')),
                ('password', models.CharField(max_length=100, verbose_name='密码')),
                ('result', models.JSONField(default=dict, verbose_name='结果')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='node_mgmt.controllertask', verbose_name='任务')),
            ],
            options={
                'verbose_name': '控制器任务节点',
                'verbose_name_plural': '控制器任务节点',
            },
        ),
        migrations.CreateModel(
            name='Controller',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated Time')),
                ('created_by', models.CharField(default='', max_length=32, verbose_name='Creator')),
                ('updated_by', models.CharField(default='', max_length=32, verbose_name='Updater')),
                ('os', models.CharField(choices=[('linux', 'Linux'), ('windows', 'Windows')], max_length=50, verbose_name='操作系统类型')),
                ('name', models.CharField(max_length=100, verbose_name='控制器名称')),
                ('description', models.TextField(blank=True, verbose_name='控制器描述')),
            ],
            options={
                'verbose_name': '控制器信息',
                'verbose_name_plural': '控制器信息',
                'unique_together': {('os', 'name')},
            },
        ),
        migrations.CreateModel(
            name='CollectorTaskNode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(max_length=100, verbose_name='任务状态')),
                ('result', models.JSONField(default=dict, verbose_name='结果')),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='node_mgmt.node', verbose_name='节点')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='node_mgmt.collectortask', verbose_name='任务')),
            ],
            options={
                'verbose_name': '采集器任务节点',
                'verbose_name_plural': '采集器任务节点',
            },
        ),
        migrations.CreateModel(
            name='CollectorConfiguration',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated Time')),
                ('created_by', models.CharField(default='', max_length=32, verbose_name='Creator')),
                ('updated_by', models.CharField(default='', max_length=32, verbose_name='Updater')),
                ('id', models.CharField(max_length=100, primary_key=True, serialize=False, verbose_name='配置ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='配置名称')),
                ('config_template', models.TextField(blank=True, verbose_name='配置模板')),
                ('is_pre', models.BooleanField(default=False, verbose_name='是否预定义')),
                ('cloud_region', models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='node_mgmt.cloudregion', verbose_name='云区域')),
                ('collector', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='node_mgmt.collector', verbose_name='采集器')),
                ('nodes', models.ManyToManyField(blank=True, to='node_mgmt.node', verbose_name='节点')),
            ],
            options={
                'verbose_name': '采集器配置信息',
                'verbose_name_plural': '采集器配置信息',
            },
        ),
        migrations.CreateModel(
            name='ChildConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated Time')),
                ('created_by', models.CharField(default='', max_length=32, verbose_name='Creator')),
                ('updated_by', models.CharField(default='', max_length=32, verbose_name='Updater')),
                ('collect_type', models.CharField(max_length=50, verbose_name='采集对象类型')),
                ('config_type', models.CharField(max_length=50, verbose_name='配置类型')),
                ('collect_instance_id', models.CharField(db_index=True, default='', max_length=100, verbose_name='采集对象实例ID')),
                ('content', models.TextField(verbose_name='内容')),
                ('collector_config', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='node_mgmt.collectorconfiguration', verbose_name='采集器配置')),
            ],
            options={
                'verbose_name': '子配置',
                'verbose_name_plural': '子配置',
            },
        ),
        migrations.CreateModel(
            name='Action',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated Time')),
                ('created_by', models.CharField(default='', max_length=32, verbose_name='Creator')),
                ('updated_by', models.CharField(default='', max_length=32, verbose_name='Updater')),
                ('action', models.JSONField(default=list, verbose_name='操作')),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='node_mgmt.node', verbose_name='节点')),
            ],
            options={
                'verbose_name': '操作信息',
                'verbose_name_plural': '操作信息',
            },
        ),
        migrations.CreateModel(
            name='SidecarEnv',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=100)),
                ('value', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, verbose_name='描述')),
                ('cloud_region', models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='node_mgmt.cloudregion', verbose_name='云区域')),
            ],
            options={
                'verbose_name': 'Sidecar环境变量',
                'verbose_name_plural': 'Sidecar环境变量',
                'unique_together': {('key', 'cloud_region')},
            },
        ),
        migrations.CreateModel(
            name='NodeOrganization',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated Time')),
                ('created_by', models.CharField(default='', max_length=32, verbose_name='Creator')),
                ('updated_by', models.CharField(default='', max_length=32, verbose_name='Updater')),
                ('organization', models.CharField(max_length=100, verbose_name='组织id')),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='node_mgmt.node', verbose_name='节点')),
            ],
            options={
                'verbose_name': '节点组织',
                'verbose_name_plural': '节点组织',
                'unique_together': {('node', 'organization')},
            },
        ),
    ]
