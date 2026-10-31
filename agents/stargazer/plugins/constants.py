# -*- coding: utf-8 -*-
# @File：constants.py
# @Time：2025/6/18 17:29
# @Author：bennie

"""
腾讯云API版本映射
code: https://github.com/TencentCloud/tencentcloud-sdk-python/tree/master/tencentcloud
"""
client_version_map = {
    "organization": "2021-03-31",
    "cvm": "2017-03-12",
    "trocket": "2023-03-08",  # rocketmq 5.x rocketMQ
    "cdb": "2017-03-20",  # cloudDB mysql
    "redis": "2018-04-12",
    "mongodb": "2019-07-25",
    "postgres": "2017-03-12",  # pgsql
    "tdmq": "2020-02-17",  # 腾讯云pulsar集群 包括4.x rocketMQ
    "cmq": "2019-03-04",
    "clb": "2018-03-17",  # 负载均衡
    "bmeip": "2019-06-25",  # 黑石弹性公网IP
    "ecm": "2019-07-19",  # 边缘计算机器
    "vpc": "2017-03-12",  # 私有网络
    "tke": "2018-05-25",  # 容器服务 TKE
    "cfs": "2019-07-19",  # 文件存储 腾讯云文件系统
    "domain": "2018-08-08",  # 域名
}
product_available_region_list_map = {"cmq": ["ap-beijing", "ap-chongqing", "ap-guangzhou", "ap-shanghai"]}
mysql_status_map = {
    0: "创建中",
    1: "运行中",
    4: "正在进行隔离操作",
    5: "已隔离",
}
mysql_pay_type_map = {
    0: "包年包月",
    1: "按量计费",
}
redis_region_map = {
    1: "广州",
    4: "上海",
    5: "中国香港",
    7: "上海金融",
    8: "北京",
    9: "新加坡",
    11: "深圳金融",
    15: "美西（硅谷）",
    16: "成都",
    17: "法兰克福",
    18: "美东（弗吉尼亚）",
    19: "重庆",
    22: "美东（弗吉尼亚）",
    23: "曼谷",
    25: "东京",
}
redis_status_map = {
    0: "待初始化",
    1: "实例在流程中",
    2: "运行中",
    -2: "实例已隔离",
    -3: "实例待删除",
}
redis_sub_status_map = {0: "磁盘读写", 1: "磁盘超限只读"}
redis_type_map = {
    2: "Redis 2.8标准版",
    3: "CKV 3.2标准版",
    4: "CKV 3.2集群版",
    5: "Redis 2.8单机版",
    6: "Redis 4.0标准版",
    7: "Redis 4.0集群版",
    8: "Redis 5.0标准版",
    9: "Redis 5.0集群版",
    15: "Redis 6.2标准版",
    16: "Redis 6.2集群版",
}

mongodb_status_map = {0: "创建中", 1: "流程处理中", 2: "运行中", -2: "实例已过期"}
mongodb_inst_type_map = {1: "正式实例", 2: "临时实例", 3: "只读实例", 4: "灾备实例"}
mongodb_pay_type_map = {0: "按量计费", 1: "包年包月"}

pgsql_status_map = {
    "applying": "申请中",
    "init": "待初始化",
    "initing": "初始化中",
    "running": "运行中",
    "limited run": "受限运行",
    "isolating": "隔离中",
    "isolated": "已隔离",
    "disisolating": "解隔离中",
    "recycling": "回收中",
    "recycled": "已回收",
    "job running": "任务执行中",
    "offline": "下线",
    "migrating": "迁移中",
    # "expanding": "扩容中", # 文档给出的状态重复 【变配中】
    "waitSwitch": "等待切换",
    "switching": "切换中",
    "readonly": "只读",
    "restarting": "重启中",
    "network changing": "网络变更中",
    "upgrading": "内核版本升级中",
    "audit-switching": "审计状态变更中",
    "primary-switching": "主备切换中",
    "offlining": "下线中",
    "deployment changing": "可用区变更中",
    "cloning": "恢复数据中",
    "parameter modifying": "参数修改中",
    "log-switching": "日志状态变更中",
    "restoring": "恢复中",
    "expanding": "变配中",
}
pgsql_pay_type_map = {"prepaid": "包年包月,预付费", "postpaid": "按量计费，后付费"}
pulsar_status_map = {0: "创建中", 1: "正常", 2: "销毁中", 3: "已删除", 4: "隔离中", 5: "创建失败", 6: "删除失败"}
pulsar_pay_type_map = {0: "按量计费", 1: "包年包月"}
cmq_status_map = {0: "仅同步元数据", 1: "迁移中", 2: "已经迁移完毕", 3: "回切状态", 4: "未迁移"}

cmq_topic_status_map = {0: "未迁移", 1: "迁移中", 2: "已经迁移完毕", 3: "回切状态", 4: "未知状态"}
cmq_topic_filter_type_map = {1: "FilterTag", 2: "BindingKey"}
clb_status_map = {
    0: "创建中",
    1: "正常运行",
}
clb_net_type_map = {"OPEN": "公网属性", "INTERNAL": "内网属性"}
clb_isp_map = {"BGP": "多线", "CMCC": "中国移动单线", "CTCC": "中国电信单线", "CUCC": "中国联通单线"}
clb_pay_type_map = {
    "AUTO_RENEW": "自动续费",
    "MANUAL_RENEW": "手动续费",
}
eip_status_map = {"CREATING": "创建中", "BINDING": "绑定中", "BIND": "已绑定", "UNBINDING": "解绑中", "UNBIND": "已解绑", "OFFLINING": "释放中", "BIND_ENI": "绑定悬空弹性网卡"}
eip_type_map = {"CalcIP": "设备ip", "WanIP": "普通公网ip", "EIP": "弹性公网ip", "AnycastEIP": "加速EIP"}
eip_res_type_map = {
    "CVM": "云服务器",
    "NAT": "NAT网关",
    "HAVIP": "高可用虚拟IP",
    "ENI": "弹性网卡",
    "CLB": "内网CLB",
    "DHCPIP": "弹性内网IP",
}
eip_isp_map = {"CMCC": "移动", "CTCC": "电信", "CUCC": "联通", "BGP": "常规BGP"}
eip_pay_type_map = {
    "BANDWIDTH_PREPAID_BY_MONTH": "包月带宽预付费",
    "TRAFFIC_POSTPAID_BY_HOUR": "按小时流量后付费",
    "BANDWIDTH_POSTPAID_BY_HOUR": "按小时带宽后付费",
    "BANDWIDTH_PACKAGE": "共享带宽包",
}
cfs_status_map = {"creating": "创建中", "mounting": "挂载中", "create_failed": "创建失败", "available": "可使用", "unserviced": "停服中", "upgrading": "升级中"}
cfs_storage_type_map = {"HP": "通用性能型", "SD": "通用标准型", "TP": "turbo性能型", "TB": "turbo标准型", "THP": "吞吐型"}
domain_status_map = {
    "ok": "正常",
    "AboutToExpire": "即将到期",
    "RegisterPending": "注册中",
    "RegisterDoing": "注册中",
    "RegisterFailed": "注册失败",
    "RenewPending": "续费期",
    "RenewDoing": "续费中",
    "RedemptionPending": "赎回期",
    "RedemptionDoing": "赎回中",
    "TransferPending": "转入中",
    "TransferTransing": "转入中",
    "TransferFailed": "转入失败",
}
