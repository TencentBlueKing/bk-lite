---
sidebar_position: 1
---

# 快速入门
    
## 背景说明
随着企业数字化转型深入，SRE 团队面临事件管理难题：监控、CI/CD 流水线、云资源等多类事件源分散，形成信息孤岛；传统运维工具成本高、覆盖有限，主流监控工具（如 zabbix、Prometheus）缺乏跨场景整合能力，无法从低价值繁杂事件中提炼有效信息，团队陷入 “找不准关键问题” 的困境。​
为此，告警中心产品应运而生。它以“高价值信息挖掘者” 为定位，打通多事件源实现统一管控，挖掘高价值 event，助力解决运维痛点、提升业务保障效率。

## 第一步：定义事件聚合规则（相关性规则）
路径：配置 -> 相关性规则

定义Event聚合为Alert的规则，系统内置了相关规则套餐进行选择
![alert1.png](https://static.cwoa.net/a9437b34f4a845afac9ade192f5e64b7.png)
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
    - 
## 第二步：推送Event
路径：集成 -> 告警源 -> 指南/事件

可以在“指南”中查看如何推送event，然后在各个系统中推送event，目前支持的事件源包括：Restful API
event推送成功后，在“事件”中可以看到对应的数据
![alert5.png](https://static.cwoa.net/d77279aa03604616947a03c7a395f191.png)

## 第三步：查看告警
路径：告警

等待规则生效后，可以在告警页面看到对应的告警信息，点击标题可以进入告警详情页面，查看告警相关的事件。
可以直接手工修改状态处理告警，也可以升级告警为事故进行处理
![alert6.png](https://static.cwoa.net/2fcc8ed971d8426d85f4e1eb35493cab.png)

## 第四步：升级“告警”为“事故”
- 路径：告警 -> 选择告警 -> 升级为事故
![alert7.png](https://static.cwoa.net/794163529d894627b151deebdc6f1f7f.png)
选择需要升级的告警，点击“升级为事故”按钮，填写标题、事故等级、处理事故的相关人员

- 路径：事故
在事故页面可以查看到升级的事故，点击标题可以进入事故详情页面，查看事故相关的告警
![alert8.png](https://static.cwoa.net/a00cb4152b81489f873f6336679706a9.png)
![alert9.png](https://static.cwoa.net/13c556375fb440baa763059fd6df2512.png)