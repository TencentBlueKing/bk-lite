---
sidebar_position: 2
---

# 功能介绍
## 告警Alert
Alert是原始Event由相关性聚合后产生的，是运维人员需要关注和处理的对象。Alert包含多个Event，Alert的级别由相关性规则来定义。
### 告警查看
列表的形式展示告警信息，支持多种维度的筛选和搜索，包括：告警级别、告警状态、告警源、我的告警、活跃告警、关键词检索。
![alert10.png](https://static.cwoa.net/82505b24b0824cbd8fe7dd1fe3d1bdff.png)
点击“详情”可以查看告警详情，告警详情包括告警的基本信息、关联的事件列表、告警的变更记录。


### 告警处理
告警处理包括：认领、转派、关闭、升级操作。状态流转如下：
![alert11.png](https://static.cwoa.net/1a34f46f60d84fb9a0df2129877e589f.png)

### 告警升级
当告警对应的问题已造成或即将造成 “业务中断、数据丢失、用户大规模投诉” 等严重后果时，将 “告警” 转化为 “事故”，启动更高等级应急响应流程的操作。

通过选择同类型的告警进行升级，形成一个 “事故” 进行统一处理，并拉上需要处理的相关人员，避免重复处理同类问题。
![alert7.png](https://static.cwoa.net/794163529d894627b151deebdc6f1f7f.png)



## 事故
事故Incident是Alert聚合后产生的具备严重后果的需要重点关注和处理的对象。
![alert8.png](https://static.cwoa.net/a00cb4152b81489f873f6336679706a9.png)

当前仅支持人工方式将Alert升级为Incident。后续支持规则方式产生Incident。
### 事故查看
列表方式展示事故信息，支持多种维度的筛选和搜索，包括：事故级别、事故状态、关键词检索。
![alert9.png](https://static.cwoa.net/13c556375fb440baa763059fd6df2512.png)
点击事故标题可以查看事故详情，事故详情包括事故的基本信息、关联的告警列表（以甘特图、表格的形式展示）、事故的变更记录，可以在事故处理中关联相关的告警。

### 事故处理
事故处理包括：认领、转派、关闭操作。状态流转如下：
![alert12.png](https://static.cwoa.net/af6a1fef04b94746aaabd480df9e47cf.png)

## 集成
集成用于管理Event推送的告警源，支持多种类型的告警源，目前支持：Restful API、NATS方式。
### 告警源
告警源详情可以查看告警源接收的Event清单、接入指南、API接口凭据等。
![alert5.png](https://static.cwoa.net/d77279aa03604616947a03c7a395f191.png)

## 配置
### 相关性规则
相关性规则是为了挖掘低层次事件的关联性，从而聚合为高层次事件，在这里您可以定义Event到Alert、Alert到Incident的聚合规则，以减少需要处理的信息量，提高单个事件的信息价值。
![alert1.png](https://static.cwoa.net/a9437b34f4a845afac9ade192f5e64b7.png)
目前仅支持定义Event聚合为Alert的规则，系统内置了相关规则套餐进行选择，用户需要定义采用的规则和需要对应使用的窗口类型。

配置说明：
- 关闭时间：此规则产生的Alert没有处理之后自动关闭的时间。
- 类型：
  - High Level Event Aggregation：高等级Event聚合，按照event相同对象实例进行聚合，alert等级为event的最低等级，常用于单种运维对象的性能判断需要多个维度结合分析的场景，例如：服务器的性能异常、数据库的性能异常等
   
python请求示例：
```python
# -*- coding: utf8 -*-
import requests
import json
url = 'https://xxxxxxxxx/api/proxy/alerts/api/receiver_data'
data = {
  "source_id": "restful",
  "events": [
    {
      "item": "mem_Usage", # 指标
      "level": "1", # 事件等级，0-提示，1-预警，2-错误，3-致命
      "title": "主机10.10.24.62的内存使用率高",
      "value": 95, # 指标值
      "labels": {
        "resource_name": "10.10.24.62", # 资源实例名称
        "resource_type": "host" # 资源类型
      },
      "description": "主机192.168.1.1的内存使用率高"
    }
  ]
}
a = requests.post(url,json=data,headers={'Content-Type': 'application/json', 'SECRET': '从 集成/restful/指南 中获取'},verify=False)
```

- Error Scenario Handling：错误场景处理，以时间间隔作为告警产生的条件，常用于比如流水线构建场景，如果某流水线构建失败后，10分钟内没有继续操作的事件，则意味着短时间内代码问题无法解决，发出告警
python请求示例：
```python
# -*- coding: utf8 -*-
import requests
import json
url = 'https://xxxxxxxxx/api/proxy/alerts/api/receiver_data'
data = {
  "source_id": "restful",
  "events": [
      {
          "item": "jenkins_build_status", # 指标：流水线构建状态
          "level": "1",
          "title": "Test Jenkins流水线 canway-gpu-release 构建失败 (#65)",
          "value": 0, # 指标值，0-失败，1-成功
          "labels": {
              "resource_name": "canway-gpu-release", # 流水线名称
              "resource_type": "jenkins" # 资源类型：jenkins
          },
          "description": "流水线: canway-gpu-release 构建失败，构建链接: http://jenkins.weops.proc/job/canway-gpu-release/65/"
      }
  ]
}
a = requests.post(url,json=data,headers={'Content-Type': 'application/json', 'SECRET': '从 集成/restful/指南 中获取'},verify=False)
```
- 作用范围：定义规则作用的Event范围，暂时为全部
- 窗口类型：定义规则生效的作用方式
    - 固定窗口：也叫做滚动窗口，特点是时间长度固定（即系统每一次会处理这个窗口内的数据），并且窗口之间不会重叠。这种窗口处理机制常适用于对时间范围有明确要求的聚合类计算，比如每分钟的用户访问量统计就可以用固定窗口。
  ![alert2.png](https://static.cwoa.net/c7de74d1a7ea4449bb198d10c4b34312.png)
    - 滑动窗口：滑动窗口有两个关键参数，分别是窗口大小和滑动步长。它会以固定的步长向前滑动，窗口之间是存在重叠的。例如，窗口大小为 10 秒，滑动步长为 5 秒，那么就会生成[0-10]、[5-15]、[10-20]等窗口。适用于规则：High Level Event Aggregation
  ![alert3.png](https://static.cwoa.net/6056cf91d17f47dab967b45c53f2f834.png)
    - 会话窗口：会话窗口的边界是由事件之间的间隔时间（会话超时时间）来确定的。如果在规定时间内没有新的事件到来，当前窗口就会关闭，后续的新事件会开启一个新的窗口。适用于：Error Scenario Handling
  ![alert4.png](https://static.cwoa.net/a8432a61410c4e6bb7bec2904066417f.png)
    
### 告警分派
配置自动分派策略，让符合筛选条件的告警，分派给指定人员，并可选择通知方式（通知方式在“Setting系统管理应用/通知渠道 中配置”）
![alert15.png](https://static.cwoa.net/65bec31304774ff8b27a47dc853af3aa.png)
配置说明：
- 匹配规则：本质是定义针对告警的筛选规则
- 分派人员：自动分派的目标人员
- 通知方式：告警分派后，通知目标人员的方式
- 高级/生效时间：定义这个分派生效的时间段，支持单次、每天、每周、每月的时间段配置
- 高级/通知场景：当前仅支持：分派
- 通知频率：支持不同告警等级在告警未响应时，不同的通知频率配置
### 屏蔽策略
定义告警的屏蔽规则，符合规则的告警将不会产生。支持单次、每天、每周、每月的时间段配置
![alert13.png](https://static.cwoa.net/89814c631fc441b3915f72f9f5caa393.png)
### 全局配置
定义未分派告警通知策略，当有未分派的告警时，通知告警指定的负责人
![alert14.png](https://static.cwoa.net/dcfd3d2ac6364a0ea56cc9d1b77fee0b.png)