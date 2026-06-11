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
      description: '容器重启次数，用于识别不稳定容器。',
      unit: 'counts',
      query: 'docker_container_status_restart_count{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'docker_container_restart_recent',
      display_name: '近 1h 重启次数',
      description: '由重启计数推导的最近 1 小时重启增量，区分“正在发生”的崩溃循环与历史遗留。',
      unit: 'counts',
      query: 'clamp_min(increase(docker_container_status_restart_count{__$labels__}[1h]), 0)',
      color: '#ff4d4f'
    },
    {
      name: 'docker_container_cpu_usage_percent',
      display_name: '容器 CPU 使用率',
      description: '容器 CPU 使用百分比。',
      unit: 'percent',
      query: 'docker_container_cpu_usage_percent{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'docker_container_mem_usage_percent',
      display_name: '容器内存使用率',
      description: '容器内存使用百分比。',
      unit: 'percent',
      query: 'docker_container_mem_usage_percent{__$labels__}',
      color: '#8a5cff'
    },
    {
      name: 'docker_container_mem_usage',
      display_name: '容器内存使用量',
      description: '容器当前内存使用量。',
      unit: 'bytes',
      query: 'docker_container_mem_usage{__$labels__}',
      color: '#8a5cff'
    },
    {
      name: 'docker_container_blkio_io_service_bytes_recursive_read_rate',
      display_name: '块设备读取速率',
      description: '容器块设备读取字节速率。',
      unit: 'byteps',
      query: 'rate(docker_container_blkio_io_service_bytes_recursive_read{__$labels__}[5m])',
      color: '#13c2c2'
    },
    {
      name: 'docker_container_blkio_io_service_bytes_recursive_write_rate',
      display_name: '块设备写入速率',
      description: '容器块设备写入字节速率。',
      unit: 'byteps',
      query: 'rate(docker_container_blkio_io_service_bytes_recursive_write{__$labels__}[5m])',
      color: '#ff8a1f'
    },
    {
      name: 'docker_container_net_rx_bytes_rate',
      display_name: '网络接收速率',
      description: '容器网络接收字节速率。',
      unit: 'byteps',
      query: 'rate(docker_container_net_rx_bytes{__$labels__}[5m])',
      color: '#2f6bff'
    },
    {
      name: 'docker_container_net_tx_bytes_rate',
      display_name: '网络发送速率',
      description: '容器网络发送字节速率。',
      unit: 'byteps',
      query: 'rate(docker_container_net_tx_bytes{__$labels__}[5m])',
      color: '#27c274'
    },
    {
      name: 'docker_container_net_rx_errors_rate',
      display_name: '网络接收错误速率',
      description: '容器网络接收错误速率。',
      unit: 'cps',
      query: 'rate(docker_container_net_rx_errors{__$labels__}[5m])',
      color: '#ff4d4f'
    },
    {
      name: 'docker_container_net_tx_errors_rate',
      display_name: '网络发送错误速率',
      description: '容器网络发送错误速率。',
      unit: 'cps',
      query: 'rate(docker_container_net_tx_errors{__$labels__}[5m])',
      color: '#faad14'
    },
  ],
  summaryCards: [
    {
      title: '运行容器数',
      metric: 'docker_n_containers_running',
      color: '#27c274',
      icon: 'node',
      guide: [{ label: '运行容器', detail: '当前处于运行状态的容器数量，反映 Docker 主机承载规模。' }],
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
      title: '重启风险',
      metric: 'docker_container_restart_recent',
      unit: 'counts',
      color: '#ff4d4f',
      icon: 'thunder',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '重启风险', detail: '近 1 小时容器重启增量，非零代表正在发生的崩溃循环，优先排查。' }],
      footer: [{ label: '停止数', metric: 'docker_n_containers_stopped', unit: 'counts' }]
    },
    {
      title: '容器 CPU 使用率',
      metric: 'docker_container_cpu_usage_percent',
      color: '#2f6bff',
      icon: 'thunder',
      guide: [{ label: 'CPU 使用率', detail: '容器 CPU 占其 CPU 配额的百分比;持续接近 100% 表示算力打满,需扩容或限流。' }],
      footer: [{ label: '内存使用率', metric: 'docker_container_mem_usage_percent', unit: 'percent' }]
    },
    {
      title: '容器内存使用率',
      metric: 'docker_container_mem_usage_percent',
      color: '#8a5cff',
      icon: 'database',
      guide: [{ label: '内存使用率', detail: '容器已用内存占其内存上限的百分比;逼近 100% 可能触发 OOM 被杀。' }],
      footer: [{ label: '内存使用量', metric: 'docker_container_mem_usage', unit: 'bytes' }]
    }
  ],
  charts: [
    {
      title: '容器资源使用趋势',
      subtitle: 'CPU、内存变化',
      metric: 'docker_container_cpu_usage_percent',
      guide: [{ label: '资源使用', detail: '对比容器 CPU 与内存使用率，识别资源压力峰值。' }],
      series: [
        { metric: 'docker_container_cpu_usage_percent', label: 'CPU 使用率', color: '#2f6bff', unit: 'percent' },
        { metric: 'docker_container_mem_usage_percent', label: '内存使用率', color: '#8a5cff', unit: 'percent' }
      ]
    },
    {
      title: '网络吞吐趋势',
      subtitle: '接收、发送流量',
      metric: 'docker_container_net_rx_bytes_rate',
      guide: [{ label: '网络吞吐', detail: '容器网络接收与发送字节速率变化。' }],
      series: [
        { metric: 'docker_container_net_rx_bytes_rate', label: '接收速率', color: '#2f6bff', unit: 'byteps' },
        { metric: 'docker_container_net_tx_bytes_rate', label: '发送速率', color: '#27c274', unit: 'byteps' }
      ]
    },
    {
      title: '块设备吞吐趋势',
      subtitle: '读写吞吐',
      metric: 'docker_container_blkio_io_service_bytes_recursive_read_rate',
      guide: [{ label: '块设备吞吐', detail: '容器块设备读写字节速率，用于观察磁盘 IO 压力。' }],
      series: [
        { metric: 'docker_container_blkio_io_service_bytes_recursive_read_rate', label: '读取速率', color: '#13c2c2', unit: 'byteps' },
        { metric: 'docker_container_blkio_io_service_bytes_recursive_write_rate', label: '写入速率', color: '#ff8a1f', unit: 'byteps' }
      ]
    },
  ],
  barPanels: [
    {
      title: '容器异常信号',
      subtitle: '网络错误速率',
      showTrend: true,
      guide: [{ label: '异常信号', detail: '容器网络接收/发送错误速率。重启增量已提为「重启风险」KPI。' }],
      items: [
        { label: '接收错误', metric: 'docker_container_net_rx_errors_rate', color: '#ff8a1f', unit: 'cps' },
        { label: '发送错误', metric: 'docker_container_net_tx_errors_rate', color: '#faad14', unit: 'cps' }
      ]
    }
  ],
  details: [
    {
      title: '容器运行详情',
      subtitle: '状态、CPU、重启与内存',
      rows: [
        { label: 'CPU 使用率', metric: 'docker_container_cpu_usage_percent', unit: 'percent' },
        { label: '重启次数', metric: 'docker_container_status_restart_count', unit: 'counts' },
        { label: '内存使用量', metric: 'docker_container_mem_usage', unit: 'bytes' }
      ]
    }
  ]
};
