import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

// 共享无线设备仪表盘：覆盖 bk-lite Wireless 对象下的 SNMP 插件（首品牌 Cambium）。
// 接口-only 基线：仅采集 IF-MIB 64 位 HC 接口流量（ifHCInOctets/ifHCOutOctets）+ 运行时长。
// 无线信号/SNR/客户端数等健康指标为 per-row 索引表（需行级过滤），telegraf 无法采集 → 不展示。
// 取不到的实例对应卡片/趋势显示「--」/空，不伪造。
export const WIRELESS_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'wireless',
  pageTitle: '无线设备监控仪表盘',
  objectFallbackName: 'Wireless',
  instanceType: 'wireless',
  collectionStatusQuery:
    "count({instance_type='wireless', __$labels__}) by (instance_id)",
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
      name: 'device_total_incoming_traffic',
      display_name: '入向总流量',
      description: '设备所有接口入向流量速率之和（字节/秒），取自 64 位 ifHCInOctets。',
      unit: 'byteps',
      query:
        '(sum(rate(interface_ifHCInOctets{__$labels__}[5m])) by (instance_id)) or (sum(rate(interface_ifInOctets{__$labels__}[5m])) by (instance_id))',
      color: '#27c274'
    },
    {
      name: 'device_total_outgoing_traffic',
      display_name: '出向总流量',
      description: '设备所有接口出向流量速率之和（字节/秒），取自 64 位 ifHCOutOctets。',
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
      title: '设备收发流量趋势',
      subtitle: '入向、出向',
      metric: 'device_total_incoming_traffic',
      guide: [{ label: '收发流量', detail: '对比设备入向与出向总流量速率，识别流量突增或异常。' }],
      series: [
        { metric: 'device_total_incoming_traffic', label: '入向', color: '#27c274', unit: 'byteps' },
        { metric: 'device_total_outgoing_traffic', label: '出向', color: '#2f6bff', unit: 'byteps' }
      ]
    }
  ],
  ringPanels: [],
  statusPanels: [],
  details: []
};
