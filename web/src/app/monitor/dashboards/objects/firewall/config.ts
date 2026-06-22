import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

// 共享防火墙仪表盘：覆盖 bk-lite Firewall 对象下所有品牌 SNMP 插件
// （Fortinet / Check Point / Stormshield / Palo Alto / SonicWall / WatchGuard …）。
// 品牌间会话/连接与内存的指标名不同，用 PromQL `or` 回退链做品牌自适应：
// 取到哪个就显示哪个，取不到的实例对应卡片/趋势显示「--」/空，不伪造数据。
export const FIREWALL_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'firewall',
  pageTitle: '防火墙监控仪表盘',
  objectFallbackName: 'Firewall',
  instanceType: 'firewall',
  collectionStatusQuery:
    "count({instance_type='firewall', __$labels__}) by (instance_id)",
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
        '防火墙 CPU 使用率。品牌自适应：直报利用率（Fortinet/Check Point/SonicWall）或各核负载均值（Palo Alto/Stormshield 走 HOST-RESOURCES hrProcessorLoad）。持续偏高说明流量检测/威胁防护负载吃紧。',
      unit: 'percent',
      query: 'avg(device_cpu_usage{__$labels__}) by (instance_id)',
      color: '#2f6bff'
    },
    {
      name: 'device_memory_usage',
      display_name: '内存使用率',
      description:
        '防火墙内存使用率（百分比）。品牌自适应：①设备直报利用率（Fortinet/SonicWall）；②(总量-空闲)/总量（Check Point/Stormshield）。部分型号（Palo Alto/WatchGuard）无标准 SNMP 内存利用率，显示「--」。',
      unit: 'percent',
      query:
        'avg(device_memory_usage{__$labels__}) by (instance_id) or ((sum(device_memory_total{__$labels__}) by (instance_id) - sum(device_memory_free{__$labels__}) by (instance_id)) / sum(device_memory_total{__$labels__}) by (instance_id) * 100) or (sum(device_memory_used{__$labels__}) by (instance_id) / sum(device_memory_total{__$labels__}) by (instance_id) * 100) or (sum(device_memory_used{__$labels__}) by (instance_id) / (sum(device_memory_used{__$labels__}) by (instance_id) + sum(device_memory_free{__$labels__}) by (instance_id)) * 100)',
      color: '#ff8a1f'
    },
    {
      name: 'firewall_sessions',
      display_name: '活动会话/连接',
      description:
        '防火墙当前活动会话或连接数。品牌自适应回退：活动会话（Fortinet/Palo Alto）→ 当前连接（SonicWall）→ 活动连接（WatchGuard）→ ASQ TCP 连接（Stormshield）。反映负载与会话表压力。',
      unit: 'counts',
      query:
        'firewall_active_sessions{__$labels__} or firewall_current_connections{__$labels__} or firewall_active_connections{__$labels__} or firewall_tcp_connections{__$labels__} or firewall_pf_states{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'firewall_session_utilization',
      display_name: '会话利用率',
      description:
        '防火墙会话表利用率（百分比）。品牌自适应：设备直报（Palo Alto panSessionUtilization）→ 活动/上限计算（active_sessions/max_sessions、current/max_connections）。逼近 100% 说明会话表将满、新连接会被丢弃。无会话上限 SNMP 指标的品牌显示「--」。',
      unit: 'percent',
      query:
        'firewall_session_utilization{__$labels__} or (firewall_active_sessions{__$labels__} / firewall_max_sessions{__$labels__} * 100) or (firewall_current_connections{__$labels__} / firewall_max_connections{__$labels__} * 100)',
      color: '#9254de'
    },
    {
      name: 'firewall_vpn_tunnels',
      display_name: 'VPN 隧道数',
      description:
        '防火墙当前 IPsec VPN 隧道数量（Fortinet fgVpnTunEntStatus / Stormshield）。隧道数骤降提示站点到站点 VPN 中断或对端不可达。无 VPN 隧道 SNMP 指标的品牌显示「--」。',
      unit: 'counts',
      query: 'firewall_vpn_tunnels{__$labels__}',
      color: '#f5222d'
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
      guide: [{ label: 'CPU 使用率', detail: '防火墙 CPU 使用率，逼近 100% 说明处理能力将耗尽。' }]
    },
    {
      title: '内存使用率',
      metric: 'device_memory_usage',
      unit: 'percent',
      color: '#ff8a1f',
      icon: 'memory',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '内存使用率', detail: '整体内存使用率，持续偏高可能由会话表过大或内存泄漏导致；部分型号无此 SNMP 指标。' }]
    },
    {
      title: '活动会话/连接',
      metric: 'firewall_sessions',
      unit: 'counts',
      color: '#13c2c2',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '活动会话/连接', detail: '当前活动会话或连接数，快速攀升可能是连接洪泛或会话表逼近上限。' }]
    },
    {
      title: '会话利用率',
      metric: 'firewall_session_utilization',
      unit: 'percent',
      color: '#9254de',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '会话利用率', detail: '会话表利用率，逼近 100% 说明会话表将满、新连接会被丢弃；无会话上限的品牌显示「--」。' }]
    },
    {
      title: '入向总流量',
      metric: 'device_total_incoming_traffic',
      unit: 'byteps',
      color: '#27c274',
      icon: 'api',
      guide: [{ label: '入向总流量', detail: '设备所有接口入向流量速率之和。' }],
      footer: [{ label: '出向', metric: 'device_total_outgoing_traffic', unit: 'byteps' }]
    }
  ],
  charts: [
    {
      title: 'CPU 与内存使用率趋势',
      subtitle: 'CPU、内存',
      metric: 'device_cpu_usage',
      guide: [{ label: '资源使用率', detail: '对比 CPU 与内存使用率，两者持续高位说明防火墙负载吃紧。' }],
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
      title: '活动会话/连接趋势',
      subtitle: '会话/连接数',
      metric: 'firewall_sessions',
      guide: [{ label: '活动会话/连接', detail: '活动会话或连接数随时间变化，突增提示连接洪泛或异常流量。' }],
      series: [
        { metric: 'firewall_sessions', label: '活动会话/连接', color: '#13c2c2', unit: 'counts' }
      ]
    },
    {
      title: '会话利用率趋势',
      subtitle: '会话表利用率',
      metric: 'firewall_session_utilization',
      guide: [{ label: '会话利用率', detail: '会话表利用率随时间变化（百分比），持续逼近 100% 需扩容或排查异常连接。无会话上限的品牌显示空。' }],
      series: [
        { metric: 'firewall_session_utilization', label: '会话利用率', color: '#9254de', unit: 'percent' }
      ]
    },
    {
      title: 'VPN 隧道数趋势',
      subtitle: 'IPsec 隧道数',
      metric: 'firewall_vpn_tunnels',
      guide: [{ label: 'VPN 隧道数', detail: 'IPsec VPN 隧道数量随时间变化，骤降提示站点到站点 VPN 中断。无 VPN 隧道指标的品牌显示空。' }],
      series: [
        { metric: 'firewall_vpn_tunnels', label: 'VPN 隧道数', color: '#f5222d', unit: 'counts' }
      ]
    }
  ],
  ringPanels: [],
  statusPanels: [],
  details: []
};
