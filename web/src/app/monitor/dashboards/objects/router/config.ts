import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

// 共享路由器仪表盘：覆盖 bk-lite Router 对象下所有品牌 SNMP 插件（首品牌 Juniper MX）。
// 品牌间 CPU/内存指标名一致（device_cpu_usage/device_memory_usage，品牌私有 OID 已在各插件归一），
// 取不到的实例对应卡片/趋势显示「--」/空，不伪造。
export const ROUTER_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'router',
  pageTitle: '路由器监控仪表盘',
  objectFallbackName: 'Router',
  instanceType: 'router',
  collectionStatusQuery:
    "count({instance_type='router', __$labels__}) by (instance_id)",
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
        '路由器 CPU 使用率。品牌自适应：直报利用率或各运行实体（路由引擎/FPC）负载均值（Juniper jnxOperatingCPU）。持续偏高说明控制平面过载或路由震荡。',
      unit: 'percent',
      query: 'avg(device_cpu_usage{__$labels__}) by (instance_id)',
      color: '#2f6bff'
    },
    {
      name: 'device_memory_usage',
      display_name: '内存使用率',
      description:
        '路由器内存使用率（百分比）。品牌自适应：①设备直报利用率（Juniper jnxOperatingBuffer）；②(总量-空闲)/总量。',
      unit: 'percent',
      query:
        'avg(device_memory_usage{__$labels__}) by (instance_id) or ((sum(device_memory_total{__$labels__}) by (instance_id) - sum(device_memory_free{__$labels__}) by (instance_id)) / sum(device_memory_total{__$labels__}) by (instance_id) * 100)',
      color: '#ff8a1f'
    },
    {
      name: 'device_temperature_celsius',
      display_name: '最高温度',
      description:
        '路由器机箱最高温度（摄氏度）。品牌自适应：仅暴露温度 OID 的型号有值（华为 AR 走 HUAWEI-ENTITY-EXTENT hwEntityTemperature，已过滤 -1 未支持哨兵），软件路由（Vyatta）等无硬件传感器显示「--」。异常升高多为风扇故障或散热不良。',
      unit: 'celsius',
      query: 'max(device_temperature_celsius{__$labels__}) by (instance_id)',
      color: '#f5222d'
    },
    {
      name: 'device_fan_state',
      display_name: '风扇状态',
      description:
        '路由器风扇状态（1=正常 / 2=异常）。品牌自适应：仅有风扇状态 OID 的型号有值（华为 AR hwEntityFanState）。折线偏离 1 即散热异常。',
      unit: 'none',
      query: 'max(device_fan_state{__$labels__}) by (instance_id)',
      color: '#13c2c2'
    },
    {
      name: 'device_psu_state',
      display_name: '电源状态',
      description:
        '路由器电源模块状态（1=正常 / 2=异常）。品牌自适应：仅有电源状态 OID 的型号有值（华为 AR hwEntityPwrState，供电/冗余待机归一为正常）。折线偏离 1 即电源冗余缺失或硬件故障。',
      unit: 'none',
      query: 'max(device_psu_state{__$labels__}) by (instance_id)',
      color: '#722ed1'
    },
    {
      name: 'device_total_incoming_traffic',
      display_name: '入向总流量',
      description: '设备所有接口入向流量速率之和（字节/秒）。',
      unit: 'byteps',
      query:
        '(sum(rate(interface_ifHCInOctets{__$labels__}[5m])) by (instance_id)) or (sum(rate(interface_ifInOctets{__$labels__}[5m])) by (instance_id))',
      color: '#27c274'
    },
    {
      name: 'device_total_outgoing_traffic',
      display_name: '出向总流量',
      description: '设备所有接口出向流量速率之和（字节/秒）。',
      unit: 'byteps',
      query:
        '(sum(rate(interface_ifHCOutOctets{__$labels__}[5m])) by (instance_id)) or (sum(rate(interface_ifOutOctets{__$labels__}[5m])) by (instance_id))',
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
      guide: [{ label: '内存使用率', detail: '整体内存使用率，持续偏高可能影响转发与路由处理性能。' }]
    },
    {
      title: '最高温度',
      metric: 'device_temperature_celsius',
      unit: 'celsius',
      color: '#f5222d',
      icon: 'health',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '最高温度', detail: '机箱所有传感器中的最高温度。异常升高可能是风扇故障或散热不良；无硬件传感器的型号显示「--」。' }]
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
      guide: [{ label: '资源使用率', detail: '对比 CPU 与内存使用率，两者持续高位说明路由器负载吃紧。' }],
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
      title: '机箱温度趋势',
      subtitle: '最高温度（℃）',
      metric: 'device_temperature_celsius',
      guide: [{ label: '机箱温度', detail: '机箱最高温度随时间变化（摄氏度）。持续升高需排查风扇/散热；无硬件传感器的型号显示空。' }],
      series: [
        { metric: 'device_temperature_celsius', label: '最高温度', color: '#f5222d', unit: 'celsius' }
      ]
    },
    {
      title: '风扇状态',
      subtitle: '状态值随时间（1=正常）',
      metric: 'device_fan_state',
      guide: [{ label: '风扇状态', detail: '风扇状态值随时间变化，1 为正常；折线偏离 1（2 异常）即散热异常。无风扇状态 OID 的型号显示空。' }],
      series: [
        { metric: 'device_fan_state', label: '风扇状态', color: '#13c2c2', unit: 'none' }
      ]
    },
    {
      title: '电源状态',
      subtitle: '状态值随时间（1=正常）',
      metric: 'device_psu_state',
      guide: [{ label: '电源状态', detail: '电源模块状态值随时间变化，1 为正常；折线偏离 1 即电源冗余缺失或硬件故障。无电源状态 OID 的型号显示空。' }],
      series: [
        { metric: 'device_psu_state', label: '电源状态', color: '#722ed1', unit: 'none' }
      ]
    }
  ],
  ringPanels: [],
  statusPanels: [],
  details: []
};
