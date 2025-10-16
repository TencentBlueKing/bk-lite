# 插件接入指南
工作目录：monitor/plugins

## 内置采集器
1.以采集器名称命名目录

eg: monitor/plugins/Telegraf

2.目录下必须包含一个 `collectors.json` 文件，描述采集器的基本信息（可以有不同的系统版本）

eg: monitor/plugins/Telegraf/collectors.json

3.属性介绍

| 属性名                     | 类型   | 说明                                                         |
|----------------------------|--------|--------------------------------------------------------------|
| id                         | string | 采集器唯一标识，必须全局唯一                                  |
| name                       | string | 采集器名称                                                   |
| controller_default_run     | bool   | 是否为控制器默认运行采集器，true表示控制器默认运行该采集器    |
| icon                       | string | 采集器图标                                               |
| node_operating_system      | string | 采集器支持的操作系统，linux/windows/mac等                     |
| service_type               | string | 采集器服务类型，exec表示执行脚本，telegraf表示Telegraf采集器 |
| executable_path            | string | 可执行文件路径，exec类型采集器必填                           |
| execute_parameters         | string | 执行参数，exec类型采集器必填，支持%s占位符，表示配置文件路径   |
| validation_parameters      | string | 验证参数，exec类型采集器必填，支持%s占位符，表示配置文件路径   |
| default_template           | string | 默认配置模版，exec类型采集器必填，支持%s占位符，表示配置文件路径 |
| introduction               | string | 采集器简介                                                   |


## 内置采集文件模版
1.在采集器名称目录下以采集方式类型命名目录（维度collect_type）

eg: monitor/plugins/Telegraf/ping
eg: monitor/plugins/ActiveMQ/jmx (ActiveMQ采集器有两种配置模版)

2.采集方式目录下以采集对象实例类型命名目录（维度instance_type）
eg: monitor/plugins/ActiveMQ/jmx/activemq

3.创建文件模版
    文件模版命名规则：采集类型.配置类型.文件类型.j2
    采集类型：维度config_type
    配置类型：base/child（采集器本体配置，child为Telegraf配置，部分采集器需要用到Telegraf进行数据上报）
    文件类型：yaml/toml等

eg: monitor/plugins/ActiveMQ/jmx/activemq/activemq.base.yaml.j2   基础配置
eg: monitor/plugins/ActiveMQ/jmx/activemq/activemq.child.yaml.j2   子配置

## 内置监控插件指标配置
1.对象实例类型目录下创建 `metrics.json` 文件
eg: monitor/plugins/ActiveMQ/jmx/activemq/metrics.json
2.属性介绍

| 属性名                      | 类型    | 说明                                           |
|--------------------------|-------|----------------------------------------------|
| plugin                   | string | 插件名称，必须全局唯一                                  |
| plugin_desc              | string | 插件描述                                         |
| name                     | string | 监控对象名称                                       |
| icon                     | string | 监控对象图标                                       |
| type                     | string | 监控对象类型                                       |
| description              | string | 监控对象描述                                       |
| default_metric              | string | 监控对象默认查询指标实例的pmq                             |
| instance_id_keys              | array | 联合唯一实例ID键列表（多维度确定唯一值，如pod，接入对象cluster的实例id+pod名称） |
| supplementary_indicators              | array | 对象实例补充指标（实例列表展示）                             |
| metrics                  | array | 监控指标列表，包含多个指标对象                              |
| metrics.metric_group     | string | 指标分组名称                                       |
| metrics.name             | string | 指标名称                                         |
| metrics.display_name     | string | 指标显示名称                                       |
| metrics.instance_id_keys | array | 实例ID键列表，用于标识不同实例                             |
| metrics.data_type        | string | 数据类型，Number/String/Boolean等                  |
| metrics.unit             | string | 数据单位，如short/long等                            |
| metrics.dimensions       | array | 维度列表，用于细分指标                                  |
| metrics.dimensions.name  | string | 维度名称                                         |
| metrics.dimensions.description  | string | 维度描述                                         |
| metrics.description      | string | 指标描述                                         |


## 上传采集器
1.可以在节点管理页面找到上述采集器，上传采集器的执行文件

## 监控对象实例接入
1.监控管理集成页面找到上述监控对象插件，即可创建监控对象实例

## 内置监控策略（可选）
1.在对象实例类型目录下创建 `policy.json` 文件
eg: monitor/plugins/Telegraf/ping/ping/policy.json

2.属性介绍

| 属性名                        | 类型   | 说明                                                                   |
|----------------------------|--------|----------------------------------------------------------------------|
| object                     | string | 监控对象名称，必须与metrics.json中的name一致                                       |
| plugin                     | string | 监控插件名称，必须与metrics.json中的plugin一致                                     |
| templates                  | array  | 告警模板列表，包含多个告警模板对象                                                    |
| templates.name             | string | 告警模板名称                                                               |
| templates.alert_name       | string | 告警名称，支持占位符${metric_instance_id}和${metric_agent_id}，分别表示实例ID和Agent ID |
| templates.description      | string | 告警描述，支持占位符${metric_instance_id}和${metric_agent_id}，分别表示实例ID和Agent ID |
| templates.metric_name      | string | 监控指标名称，必须与metrics.json中的metrics.name一致                               |
| templates.algorithm        | string | 告警算法，支持last_over_time、avg_over_time等算法                               |
| templates.threshold        | array  | 告警阈值列表，包含多个阈值对象                                                      |
| templates.threshold.level  | string | 阈值级别，支持critical/error/warning等                                       |
| templates.threshold.value  | number | 阈值数值，表示触发告警的数值阈值                                                     |
| templates.threshold.method | string | 阈值对比方式                                                               |
