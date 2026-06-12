import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

export const SWITCH_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'switch',
  pageTitle: '交换机监控仪表盘',
  objectFallbackName: 'Switch',
  instanceType: 'switch',
  collectionStatusQuery:
    "count({instance_type='switch', __$labels__}) by (instance_id)",
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
      description: '设备控制平面 CPU 使用率（5 分钟平均），持续偏高说明控制平面过载或异常流量。',
      unit: 'percent',
      query: 'device_cpu_usage{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'device_memory_usage',
      display_name: '内存使用率',
      description:
        '设备整体内存使用率（百分比）。品牌自适应：优先取设备直接上报的利用率（如华为 hwEntityMemUsage），无直报值时按各内存池 已用/(已用+空闲) 汇总计算（如思科内存池）。',
      unit: 'percent',
      query:
        'avg(device_memory_usage{__$labels__}) by (instance_id) or (sum(device_memory_used{__$labels__}) by (instance_id) / (sum(device_memory_used{__$labels__}) by (instance_id) + sum(device_memory_free{__$labels__}) by (instance_id)) * 100)',
      color: '#ff8a1f'
    },
    {
      name: 'device_memory_used',
      display_name: '内存已用',
      description: '设备各内存池当前已使用的字节数之和。',
      unit: 'bytes',
      query: 'sum(device_memory_used{__$labels__}) by (instance_id)',
      color: '#ff8a1f'
    },
    {
      name: 'device_memory_free',
      display_name: '内存空闲',
      description: '设备各内存池当前空闲可用的字节数之和。',
      unit: 'bytes',
      query: 'sum(device_memory_free{__$labels__}) by (instance_id)',
      color: '#27c274'
    },
    {
      name: 'device_temperature_celsius',
      display_name: '最高温度',
      description: '设备各温度传感器读数中的最高值（摄氏度），用于一眼判断散热风险。',
      unit: 'celsius',
      query: 'max(device_temperature_celsius{__$labels__}) by (instance_id)',
      color: '#f5222d'
    },
    {
      name: 'device_fan_state',
      display_name: '风扇状态',
      description: '设备风扇的最坏运行状态。非正常状态表示散热故障，应立即排查。',
      unit: 'none',
      query: 'max(device_fan_state{__$labels__}) by (instance_id)',
      color: '#13c2c2'
    },
    {
      name: 'device_psu_state',
      display_name: '电源状态',
      description: '设备电源模块的最坏运行状态。非正常状态表示电源冗余缺失或硬件故障。',
      unit: 'none',
      query: 'max(device_psu_state{__$labels__}) by (instance_id)',
      color: '#722ed1'
    },
    {
      name: 'device_total_incoming_traffic',
      display_name: '入向总流量',
      description: '设备所有接口入向流量速率之和（字节/秒）。',
      unit: 'byteps',
      query: 'sum(rate(interface_ifInOctets{__$labels__}[5m])) by (instance_id)',
      color: '#27c274'
    },
    {
      name: 'device_total_outgoing_traffic',
      display_name: '出向总流量',
      description: '设备所有接口出向流量速率之和（字节/秒）。',
      unit: 'byteps',
      query: 'sum(rate(interface_ifOutOctets{__$labels__}[5m])) by (instance_id)',
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
      guide: [{ label: 'CPU 使用率', detail: '控制平面 CPU 使用率，逼近 100% 说明处理能力将耗尽。' }]
    },
    {
      title: '内存使用率',
      metric: 'device_memory_usage',
      unit: 'percent',
      color: '#ff8a1f',
      icon: 'memory',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '内存使用率', detail: '整体内存使用率，持续偏高可能由内存泄漏或表项过大导致。' }],
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
      guide: [{ label: '最高温度', detail: '所有传感器中的最高温度。异常升高可能是风扇故障或散热不良。' }]
    },
    {
      title: '入向总流量',
      metric: 'device_total_incoming_traffic',
      unit: 'byteps',
      color: '#27c274',
      icon: 'api',
      guide: [{ label: '入向总流量', detail: '设备所有接口入向流量速率之和。' }],
      footer: [{ label: '出向', metric: 'device_total_outgoing_traffic', unit: 'byteps' }]
    },
    {
      title: '出向总流量',
      metric: 'device_total_outgoing_traffic',
      unit: 'byteps',
      color: '#2f6bff',
      icon: 'api',
      guide: [{ label: '出向总流量', detail: '设备所有接口出向流量速率之和。' }]
    }
  ],
  charts: [
    {
      title: 'CPU 与内存使用率趋势',
      subtitle: 'CPU、内存',
      metric: 'device_cpu_usage',
      guide: [{ label: '资源使用率', detail: '对比 CPU 与内存使用率，两者持续高位说明设备负载吃紧。' }],
      series: [
        { metric: 'device_cpu_usage', label: 'CPU 使用率', color: '#2f6bff', unit: 'percent' },
        { metric: 'device_memory_usage', label: '内存使用率', color: '#ff8a1f', unit: 'percent' }
      ]
    },
    {
      title: '设备收发流量趋势',
      subtitle: '入向、出向',
      metric: 'device_total_incoming_traffic',
      guide: [{ label: '收发流量', detail: '对比设备入向与出向总流量速率，识别流量突增或异常。' }],
      series: [
        { metric: 'device_total_incoming_traffic', label: '入向', color: '#27c274', unit: 'byteps' },
        { metric: 'device_total_outgoing_traffic', label: '出向', color: '#2f6bff', unit: 'byteps' }
      ]
    },
    {
      title: '温度趋势',
      subtitle: '最高传感器温度',
      metric: 'device_temperature_celsius',
      guide: [{ label: '温度', detail: '设备最高传感器温度随时间变化，持续上升需关注散热。' }],
      series: [
        { metric: 'device_temperature_celsius', label: '最高温度', color: '#f5222d', unit: 'celsius' }
      ]
    },
    {
      title: '风扇状态',
      subtitle: '状态值随时间（1=正常）',
      metric: 'device_fan_state',
      guide: [{ label: '风扇状态', detail: '风扇状态值随时间变化，1 为正常；折线偏离 1（2 告警 / 3 严重 / 6 故障）即出现散热异常，可一眼看出异常时刻。' }],
      series: [
        { metric: 'device_fan_state', label: '风扇状态', color: '#13c2c2', unit: 'none' }
      ]
    },
    {
      title: '电源状态',
      subtitle: '状态值随时间（1=正常）',
      metric: 'device_psu_state',
      guide: [{ label: '电源状态', detail: '电源模块状态值随时间变化，1 为正常；折线偏离 1 即电源冗余缺失或硬件故障，可一眼看出异常时刻。' }],
      series: [
        { metric: 'device_psu_state', label: '电源状态', color: '#722ed1', unit: 'none' }
      ]
    }
  ],
  ringPanels: [],
  statusPanels: [],
  details: []
};
