import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';
import {
  GENERIC_DEVICE_TEMPERATURE_CHART_GUIDE,
  GENERIC_DEVICE_TEMPERATURE_KPI_GUIDE
} from '../common/device-temperature-guide';

// 共享 WAN 优化仪表盘：覆盖 bk-lite Wanopt 对象下的 SNMP 插件（首品牌 Exinda / GFI ExOS）。
// CPU/内存/温度走企业树标量；接口吞吐走内置 IF-MIB。取不到的实例对应卡片/趋势显示「--」/空，不伪造。
export const WANOPT_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'wanopt',
  pageTitle: 'WAN优化监控仪表盘',
  objectFallbackName: 'Wanopt',
  instanceType: 'wanopt',
  collectionStatusQuery:
    "count({instance_type='wanopt', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'snmp'],
  metrics: [
    {
      name: 'snmp_uptime',
      display_name: '运行时长',
      description: '设备自上次重启以来的持续运行时间，反映设备稳定性。',
      unit: 's',
      query: 'sum(snmp_uptime{__$labels__} / 100) by (instance_id)',
      color: '#597ef7'
    },
    {
      name: 'device_cpu_usage',
      display_name: 'CPU 使用率',
      description:
        'WAN 优化设备整机 CPU 使用率（0-100%）。持续偏高说明加速、整形或深度检测负载吃紧。',
      unit: 'percent',
      query:
        'avg(snmp_device_cpu_usage{__$labels__}) by (instance_id) or avg(device_cpu_usage{__$labels__}) by (instance_id)',
      color: '#2f6bff'
    },
    {
      name: 'device_memory_usage',
      display_name: '内存使用率',
      description: 'WAN 优化设备物理内存使用率（已用/总量）。持续偏高可能影响加速会话处理。',
      unit: 'percent',
      query:
        '(sum(snmp_device_memory_used{__$labels__}) by (instance_id) / sum(snmp_device_memory_total{__$labels__}) by (instance_id) * 100) or avg(device_memory_usage{__$labels__}) by (instance_id) or (sum(device_memory_used{__$labels__}) by (instance_id) / sum(device_memory_total{__$labels__}) by (instance_id) * 100)',
      color: '#ff8a1f'
    },
    {
      name: 'device_memory_used',
      display_name: '内存已用',
      description: 'WAN 优化设备当前已使用的物理内存。',
      unit: 'bytes',
      query:
        '(sum(snmp_device_memory_used{__$labels__}) by (instance_id) * 1024) or sum(device_memory_used{__$labels__}) by (instance_id)',
      color: '#ff8a1f'
    },
    {
      name: 'device_temperature_celsius',
      display_name: '最高温度',
      description: 'WAN 优化设备 CPU 温度（摄氏度）。异常升高多为散热不良或环境过热。',
      unit: 'celsius',
      query:
        'max(snmp_device_temperature_celsius{__$labels__}) by (instance_id) or max(device_temperature_celsius{__$labels__}) by (instance_id)',
      color: '#f5222d'
    },
    {
      name: 'device_total_incoming_traffic',
      display_name: '入向总流量',
      description: '设备所有接口入向流量速率之和（字节/秒）。',
      unit: 'byteps',
      query:
        '(sum(rate(interface_ifHCInOctets{__$labels__}[__$window__])) by (instance_id)) or (sum(rate(interface_ifInOctets{__$labels__}[__$window__])) by (instance_id))',
      color: '#27c274'
    },
    {
      name: 'device_total_outgoing_traffic',
      display_name: '出向总流量',
      description: '设备所有接口出向流量速率之和（字节/秒）。',
      unit: 'byteps',
      query:
        '(sum(rate(interface_ifHCOutOctets{__$labels__}[__$window__])) by (instance_id)) or (sum(rate(interface_ifOutOctets{__$labels__}[__$window__])) by (instance_id))',
      color: '#2f6bff'
    }
  ],
  summaryCards: [
    {
      title: '运行时长',
      metric: 'snmp_uptime',
      unit: 's',
      formatter: 'duration',
      isUptimeCard: true,
      icon: 'clock',
      color: '#597ef7',
      guide: [{ label: '运行时长', detail: '设备自上次重启后的持续运行时间；期间发生重启会重新计时。' }],
      footer: [{ label: '启动', metric: 'snmp_uptime', formatter: 'startedAt' }]
    },
    {
      title: 'CPU 使用率',
      metric: 'device_cpu_usage',
      unit: 'percent',
      color: '#2f6bff',
      icon: 'thunder',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: 'CPU 使用率', detail: '整机 CPU 使用率，逼近 100% 说明优化处理能力将耗尽。' }]
    },
    {
      title: '内存使用率',
      metric: 'device_memory_usage',
      unit: 'percent',
      color: '#ff8a1f',
      icon: 'memory',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '内存使用率', detail: '物理内存使用率，持续偏高可能影响加速会话处理。' }],
      footer: [{ label: '已用', metric: 'device_memory_used', unit: 'bytes' }]
    },
    {
      title: '最高温度',
      metric: 'device_temperature_celsius',
      unit: 'celsius',
      color: '#f5222d',
      icon: 'health',
      compare: true,
      compareFavorableDirection: 'down',
      guide: GENERIC_DEVICE_TEMPERATURE_KPI_GUIDE
    },
    {
      title: '入向总流量',
      metric: 'device_total_incoming_traffic',
      unit: 'byteps',
      color: '#27c274',
      icon: 'api',
      guide: [{ label: '入向总流量', detail: '全部接口入向字节速率；突增优先查广播风暴、异常主机与上联拥塞。' }],
      footer: [{ label: '出向', metric: 'device_total_outgoing_traffic', unit: 'byteps' }]
    }
  ],
  charts: [
    {
      title: 'CPU 与内存使用率趋势',
      subtitle: 'CPU、内存',
      metric: 'device_cpu_usage',
      guide: [{ label: '资源使用率', detail: '对比 CPU 与内存使用率，两者持续高位说明 WAN 优化负载吃紧。' }],
      series: [
        { metric: 'device_cpu_usage', label: 'CPU 使用率', color: '#2f6bff', unit: 'percent' },
        { metric: 'device_memory_usage', label: '内存使用率', color: '#ff8a1f', unit: 'percent' }
      ]
    },
    {
      title: '设备收发流量趋势',
      subtitle: '入向、出向',
      metric: 'device_total_incoming_traffic',
      guide: [{ label: '收发流量', detail: '对比入/出向总流量；突增查风暴与上联，持续高水位结合接口错误计数排查。' }],
      series: [
        { metric: 'device_total_incoming_traffic', label: '入向', color: '#27c274', unit: 'byteps' },
        { metric: 'device_total_outgoing_traffic', label: '出向', color: '#2f6bff', unit: 'byteps' }
      ]
    },
    {
      title: '机箱温度趋势',
      subtitle: '最高温度（℃）',
      metric: 'device_temperature_celsius',
      guide: GENERIC_DEVICE_TEMPERATURE_CHART_GUIDE,
      series: [
        { metric: 'device_temperature_celsius', label: '最高温度', color: '#f5222d', unit: 'celsius' }
      ]
    }
  ],
  ringPanels: [],
  statusPanels: [],
  details: []
};
