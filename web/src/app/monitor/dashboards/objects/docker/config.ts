import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

export const DOCKER_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'docker',
  pageTitle: 'Docker 监控仪表盘',
  objectFallbackName: 'Docker',
  instanceType: 'docker',
  collectionStatusQuery: "count({instance_type='docker', collect_type='docker', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'docker'],
  metrics: [
    {
      name: 'docker_n_containers_running',
      display_name: '运行容器数',
      description: 'Docker 主机上当前处于运行状态的容器数量。',
      unit: 'counts',
      query: 'docker_n_containers_running{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'docker_n_containers',
      display_name: '总容器数',
      description: 'Docker 主机上的容器总数量。',
      unit: 'counts',
      query: 'docker_n_containers{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'docker_n_containers_stopped',
      display_name: '停止容器数',
      description: 'Docker 主机上当前停止的容器数量。',
      unit: 'counts',
      query: 'docker_n_containers_stopped{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'docker_stopped_pct',
      display_name: '停止容器占比',
      description: '由停止容器数与总容器数推导出的停止占比（停止 / 总容器），反映容器存活健康度。',
      unit: 'percent',
      query: 'clamp_max(100 * (docker_n_containers_stopped{__$labels__} / clamp_min(docker_n_containers{__$labels__}, 1)), 100)',
      color: '#ff8a1f'
    },
    {
      name: 'docker_container_status_restart_count',
      display_name: '容器重启次数',
      description: '主机下所有容器重启次数合计，用于识别不稳定容器。',
      unit: 'counts',
      query: 'sum(docker_container_status_restart_count{__$labels__}) by (instance_id)',
      color: '#ff8a1f'
    },
    {
      name: 'docker_container_restart_recent',
      display_name: '时段内重启',
      description: '当前所选时间范围内，主机下所有容器重启增量合计；区分期间新发生的崩溃循环与历史遗留。速率/增量窗口与时间选择器一致。',
      unit: 'counts',
      query: 'clamp_min(sum(increase(docker_container_status_restart_count{__$labels__}[__$window__])) by (instance_id), 0)',
      color: '#ff4d4f'
    },
    {
      name: 'docker_container_cpu_usage_percent',
      display_name: '容器 CPU 使用率',
      description: '主机下各容器 CPU 使用率的最大值，用于发现算力打满的容器。',
      unit: 'percent',
      query: 'max(docker_container_cpu_usage_percent{__$labels__}) by (instance_id)',
      color: '#2f6bff'
    },
    {
      name: 'docker_container_mem_usage_percent',
      display_name: '容器内存使用率',
      description: '主机下各容器内存使用率的最大值，用于发现逼近内存上限的容器。',
      unit: 'percent',
      query: 'max(docker_container_mem_usage_percent{__$labels__}) by (instance_id)',
      color: '#8a5cff'
    },
    {
      name: 'docker_container_mem_usage',
      display_name: '容器内存使用量',
      description: '主机下各容器内存使用量的最大值。',
      unit: 'bytes',
      query: 'max(docker_container_mem_usage{__$labels__}) by (instance_id)',
      color: '#8a5cff'
    },
    {
      name: 'docker_container_blkio_io_service_bytes_recursive_read_rate',
      display_name: '块设备读取速率',
      description: '主机下容器块设备读取字节速率合计。计算窗口与时间选择器一致。',
      unit: 'byteps',
      query: 'sum(rate(docker_container_blkio_io_service_bytes_recursive_read{__$labels__}[__$window__])) by (instance_id)',
      color: '#13c2c2'
    },
    {
      name: 'docker_container_blkio_io_service_bytes_recursive_write_rate',
      display_name: '块设备写入速率',
      description: '主机下容器块设备写入字节速率合计。计算窗口与时间选择器一致。',
      unit: 'byteps',
      query: 'sum(rate(docker_container_blkio_io_service_bytes_recursive_write{__$labels__}[__$window__])) by (instance_id)',
      color: '#ff8a1f'
    },
    {
      name: 'docker_container_net_rx_bytes_rate',
      display_name: '网络接收速率',
      description: '主机下容器网络接收字节速率合计。计算窗口与时间选择器一致。',
      unit: 'byteps',
      query: 'sum(rate(docker_container_net_rx_bytes{__$labels__}[__$window__])) by (instance_id)',
      color: '#2f6bff'
    },
    {
      name: 'docker_container_net_tx_bytes_rate',
      display_name: '网络发送速率',
      description: '主机下容器网络发送字节速率合计。计算窗口与时间选择器一致。',
      unit: 'byteps',
      query: 'sum(rate(docker_container_net_tx_bytes{__$labels__}[__$window__])) by (instance_id)',
      color: '#27c274'
    },
    {
      name: 'docker_container_net_rx_errors_rate',
      display_name: '网络接收错误速率',
      description: '主机下容器网络接收错误速率合计。计算窗口与时间选择器一致。',
      unit: 'cps',
      query: 'sum(rate(docker_container_net_rx_errors{__$labels__}[__$window__])) by (instance_id)',
      color: '#ff4d4f'
    },
    {
      name: 'docker_container_net_tx_errors_rate',
      display_name: '网络发送错误速率',
      description: '主机下容器网络发送错误速率合计。计算窗口与时间选择器一致。',
      unit: 'cps',
      query: 'sum(rate(docker_container_net_tx_errors{__$labels__}[__$window__])) by (instance_id)',
      color: '#faad14'
    },
  ],
  summaryCards: [
    {
      title: '运行容器数',
      metric: 'docker_n_containers_running',
      color: '#27c274',
      icon: 'node',
      guide: [{
        label: '运行容器',
        detail: '当前运行中的容器数。请对照脚注停止数与「停止容器占比」「时段内重启」：停止偏多查退出原因，时段内重启非零优先查崩溃循环。'
      }],
      footer: [{ label: '停止容器', metric: 'docker_n_containers_stopped', unit: 'counts' }]
    },
    {
      title: '停止容器占比',
      metric: 'docker_stopped_pct',
      unit: 'percent',
      color: '#ff8a1f',
      icon: 'database',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '停止容器占比', detail: '停止容器占总容器的比例，越高说明越多容器处于非运行状态，需排查异常退出原因。' }],
      footer: [{ label: '停止数', metric: 'docker_n_containers_stopped', unit: 'counts' }]
    },
    {
      title: '时段内重启',
      metric: 'docker_container_restart_recent',
      unit: 'counts',
      color: '#ff4d4f',
      icon: 'thunder',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{
        label: '时段内重启',
        detail: '当前所选时间范围内，主机下所有容器重启增量合计；非零代表期间发生过重启，优先排查崩溃循环。统计窗口与时间选择器一致。'
      }],
      footer: [{ label: '累计重启', metric: 'docker_container_status_restart_count', unit: 'counts' }]
    },
    {
      title: '容器 CPU 使用率',
      metric: 'docker_container_cpu_usage_percent',
      color: '#2f6bff',
      icon: 'thunder',
      guide: [{
        label: 'CPU 使用率',
        detail: '主机下各容器 CPU 使用率的最大值；持续接近 100% 表示至少有一个容器算力打满，需扩容或限流。'
      }]
    },
    {
      title: '容器内存使用率',
      metric: 'docker_container_mem_usage_percent',
      color: '#8a5cff',
      icon: 'database',
      guide: [{
        label: '内存使用率',
        detail: '主机下各容器内存使用率的最大值；逼近 100% 时至少有一个容器可能触发 OOM。脚注为对应口径下的最大内存使用量。'
      }],
      footer: [{ label: '最大使用量', metric: 'docker_container_mem_usage', unit: 'bytes' }]
    }
  ],
  charts: [
    {
      title: '容器资源使用趋势',
      subtitle: 'CPU、内存最大使用率',
      metric: 'docker_container_cpu_usage_percent',
      guide: [{
        label: '资源使用',
        detail: '主机下容器 CPU/内存使用率的最大值趋势，用于识别资源压力峰值。'
      }],
      series: [
        { metric: 'docker_container_cpu_usage_percent', label: 'CPU 最大使用率', color: '#2f6bff', unit: 'percent' },
        { metric: 'docker_container_mem_usage_percent', label: '内存最大使用率', color: '#8a5cff', unit: 'percent' }
      ]
    },
    {
      title: '网络吞吐趋势',
      subtitle: '接收、发送合计',
      metric: 'docker_container_net_rx_bytes_rate',
      guide: [{
        label: '网络吞吐',
        detail: '主机下容器网络收发字节速率合计。速率计算窗口与时间选择器一致（长窗会更平滑）。与右侧错误对照：吞吐正常但错误持续非零，优先查网卡/策略/对端；两者同时抬升，再看是否流量冲击。'
      }],
      series: [
        { metric: 'docker_container_net_rx_bytes_rate', label: '接收速率', color: '#2f6bff', unit: 'byteps' },
        { metric: 'docker_container_net_tx_bytes_rate', label: '发送速率', color: '#27c274', unit: 'byteps' }
      ]
    },
    {
      title: '网络错误速率',
      subtitle: '接收、发送错误合计',
      metric: 'docker_container_net_rx_errors_rate',
      guide: [{
        label: '网络错误速率',
        detail: '主机下容器收/发错误速率合计。健康基线通常接近 0：持续非零先查网卡、网络策略与对端连通性；若左侧吞吐同时异常，再区分拥塞与链路故障。计算窗口与时间选择器一致。'
      }],
      series: [
        { metric: 'docker_container_net_rx_errors_rate', label: '接收错误', color: '#ff8a1f', unit: 'cps' },
        { metric: 'docker_container_net_tx_errors_rate', label: '发送错误', color: '#faad14', unit: 'cps' }
      ]
    },
    {
      title: '块设备吞吐趋势',
      subtitle: '读取、写入合计',
      metric: 'docker_container_blkio_io_service_bytes_recursive_read_rate',
      guide: [{
        label: '块设备吞吐',
        detail: '主机下容器块设备读写字节速率合计，用于观察磁盘 IO 压力。计算窗口与时间选择器一致（长窗会更平滑）。'
      }],
      series: [
        { metric: 'docker_container_blkio_io_service_bytes_recursive_read_rate', label: '读取速率', color: '#13c2c2', unit: 'byteps' },
        { metric: 'docker_container_blkio_io_service_bytes_recursive_write_rate', label: '写入速率', color: '#ff8a1f', unit: 'byteps' }
      ]
    },
  ],
  barPanels: [],
  details: []
};
