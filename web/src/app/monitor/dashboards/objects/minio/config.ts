import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

const CLUSTER_HEALTH_ENUM = {
  1: { label: '可服务', color: '#27c274' },
  0: { label: '不可服务', color: '#ff4d4f' }
};

const ERASURE_STATUS_ENUM = {
  1: { label: '完整', color: '#27c274' },
  0: { label: '降级', color: '#ff4d4f' }
};

/**
 * MinIO 专业盘：对象存储集群健康 + 可用容量 + 纠删组冗余 + S3 服务。
 * Metrics v3 查询在前，Metrics v2 通过 PromQL `or` 回退；两侧均使用真实指标名。
 */
export const MINIO_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'minio',
  pageTitle: 'MinIO 监控仪表盘',
  objectFallbackName: 'Minio',
  instanceType: 'minio',
  collectionStatusQuery:
    "count({instance_type='minio', collect_type='bkpull', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'bkpull', 'Object Storage'],
  metrics: [
    {
      name: 'minio_cluster_health',
      display_name: '集群健康状态',
      description: '集群整体健康：1 健康、0 不健康。',
      unit: 'none',
      query:
        'max by (instance_id) (minio_cluster_erasure_set_overall_health_gauge{__$labels__}) or max by (instance_id) (minio_cluster_health_status_gauge{__$labels__})',
      color: '#27c274'
    },
    {
      name: 'minio_erasure_status',
      display_name: '纠删组状态',
      description: '纠删组（Erasure Set）健康状态。',
      unit: 'none',
      query:
        'min by (instance_id) (minio_cluster_erasure_set_overall_health_gauge{__$labels__}) or min by (instance_id) (minio_cluster_health_erasure_set_status_gauge{__$labels__})',
      color: '#2f6bff'
    },
    {
      name: 'minio_usable_free',
      display_name: '可用空闲容量',
      description: '集群可用逻辑空闲容量。',
      unit: 'bytes',
      query:
        'max by (instance_id) (minio_cluster_health_capacity_usable_free_bytes_gauge{__$labels__}) or max by (instance_id) (minio_cluster_capacity_usable_free_bytes_gauge{__$labels__})',
      color: '#13c2c2'
    },
    {
      name: 'minio_usable_total',
      display_name: '可用总容量',
      description: '纠删编码后的可用逻辑总容量。',
      unit: 'bytes',
      query:
        'max by (instance_id) (minio_cluster_health_capacity_usable_total_bytes_gauge{__$labels__}) or max by (instance_id) (minio_cluster_capacity_usable_total_bytes_gauge{__$labels__})',
      color: '#2f6bff'
    },
    {
      name: 'minio_usable_used_pct',
      display_name: '可用容量使用率',
      description: '已用可用容量占总可用容量的比例。',
      unit: 'percent',
      query:
        'clamp_min(100 * (1 - minio_cluster_health_capacity_usable_free_bytes_gauge{__$labels__} / clamp_min(minio_cluster_health_capacity_usable_total_bytes_gauge{__$labels__}, 1)), 0) or clamp_min(100 * (1 - minio_cluster_capacity_usable_free_bytes_gauge{__$labels__} / clamp_min(minio_cluster_capacity_usable_total_bytes_gauge{__$labels__}, 1)), 0)',
      color: '#ff8a1f'
    },
    {
      name: 'minio_drives_online',
      display_name: '在线驱动器数',
      description: '当前在线可用存储驱动器数量。',
      unit: 'counts',
      query:
        'max by (instance_id) (minio_cluster_health_drives_online_count_gauge{__$labels__}) or max by (instance_id) (minio_cluster_drive_online_total_gauge{__$labels__})',
      color: '#27c274'
    },
    {
      name: 'minio_nodes_online',
      display_name: '在线节点数',
      description: '当前在线服务器节点数。',
      unit: 'counts',
      query:
        'max by (instance_id) (minio_cluster_health_nodes_online_count_gauge{__$labels__}) or max by (instance_id) (minio_cluster_nodes_online_total_gauge{__$labels__})',
      color: '#597ef7'
    },
    {
      name: 'minio_erasure_drives',
      display_name: '纠删组在线盘',
      description: '纠删组内在线驱动器数。',
      unit: 'counts',
      query:
        'min by (instance_id) (minio_cluster_erasure_set_online_drives_count_gauge{__$labels__}) or min by (instance_id) (minio_cluster_health_erasure_set_online_drives_gauge{__$labels__})',
      color: '#8a5cff'
    },
    {
      name: 'minio_s3_rx_rate',
      display_name: 'S3 接收流量',
      description: 'S3 接收字节速率。',
      unit: 'byteps',
      query:
        'sum by (instance_id) (rate(minio_api_requests_traffic_received_bytes_counter{__$labels__}[__$window__])) or sum by (instance_id) (rate(minio_s3_traffic_received_bytes_counter{__$labels__}[__$window__]))',
      color: '#2f6bff'
    },
    {
      name: 'minio_s3_tx_rate',
      display_name: 'S3 发送流量',
      description: 'S3 发送字节速率。',
      unit: 'byteps',
      query:
        'sum by (instance_id) (rate(minio_api_requests_traffic_sent_bytes_counter{__$labels__}[__$window__])) or sum by (instance_id) (rate(minio_s3_traffic_sent_bytes_counter{__$labels__}[__$window__]))',
      color: '#13c2c2'
    },
    {
      name: 'minio_s3_incoming',
      display_name: '进行中的 S3 请求',
      description: '当前正在处理的入向 S3 请求数。',
      unit: 'counts',
      query:
        'sum by (instance_id) (minio_api_requests_incoming_total_gauge{__$labels__}) or sum by (instance_id) (minio_s3_requests_incoming_total_gauge{__$labels__})',
      color: '#27c274'
    },
    {
      name: 'minio_s3_waiting',
      display_name: '等待中的 S3 请求',
      description: '当前等待处理的 S3 请求数。',
      unit: 'counts',
      query:
        'sum by (instance_id) (minio_api_requests_waiting_total_gauge{__$labels__}) or sum by (instance_id) (minio_s3_requests_waiting_total_gauge{__$labels__})',
      color: '#ff8a1f'
    },
    {
      name: 'minio_s3_auth_reject_rate',
      display_name: '鉴权拒绝速率',
      description: '因认证失败被拒绝的 S3 请求速率。',
      unit: 'cps',
      query:
        'sum by (instance_id) (rate(minio_api_requests_rejected_auth_total_counter{__$labels__}[__$window__])) or sum by (instance_id) (rate(minio_s3_requests_rejected_auth_total_counter{__$labels__}[__$window__]))',
      color: '#ff4d4f'
    },
    {
      name: 'minio_5xx_error_rate',
      display_name: '5xx 错误速率',
      description: '服务端错误请求速率，v3 优先并回退到 v2。',
      unit: 'cps',
      query:
        'sum by (instance_id) (rate(minio_api_requests_5xx_errors_total_counter{__$labels__}[__$window__])) or sum by (instance_id) (rate(minio_s3_requests_5xx_errors_total_counter{__$labels__}[__$window__]))',
      color: '#ff4d4f'
    },
    {
      name: 'minio_mem_used_pct',
      display_name: '节点内存使用率',
      description: '节点内存使用率（取最大值以覆盖压力最高节点）。',
      unit: 'percent',
      query:
        'max by (instance_id) (minio_system_memory_used_perc_gauge{__$labels__}) or max by (instance_id) (minio_node_mem_used_perc_gauge{__$labels__})',
      color: '#8a5cff'
    },
    {
      name: 'minio_drive_util_max',
      display_name: '驱动器使用率峰值',
      description: '单盘使用率峰值。',
      unit: 'percent',
      query:
        'max by (instance_id) (minio_system_drive_perc_util_gauge{__$labels__}) or max by (instance_id) (minio_node_drive_perc_util_gauge{__$labels__})',
      color: '#ff8a1f'
    }
  ],
  summaryCards: [
    {
      title: '集群状态',
      metric: 'minio_cluster_health',
      color: '#27c274',
      icon: 'health',
      enumMap: CLUSTER_HEALTH_ENUM,
      guide: [
        {
          label: '可服务 / 不可服务',
          detail: '集群整体能否对外提供对象读写。不可服务时先查节点、驱动器是否掉线。'
        },
        {
          label: '纠删冗余',
          detail: '纠删组数据冗余是否完整：完整=容错能力正常；降级=有盘离线或冗余不足，仍可能可读但风险升高。'
        }
      ],
      footer: [{ label: '纠删冗余', metric: 'minio_erasure_status', enumMap: ERASURE_STATUS_ENUM }]
    },
    {
      title: '可用空闲容量',
      metric: 'minio_usable_free',
      unit: 'bytes',
      color: '#13c2c2',
      icon: 'database',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [
        {
          label: '空闲容量',
          detail: '纠删编码后的可用逻辑空闲容量。持续下降需扩容或清理对象。'
        }
      ],
      footer: [{ label: '使用率', metric: 'minio_usable_used_pct', unit: 'percent' }]
    },
    {
      title: '在线驱动器',
      metric: 'minio_drives_online',
      unit: 'counts',
      color: '#27c274',
      icon: 'node',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [
        {
          label: '在线盘',
          detail: '在线驱动器数。下跌会削弱纠删冗余与吞吐。'
        }
      ],
      footer: [{ label: '在线节点', metric: 'minio_nodes_online', unit: 'counts' }]
    },
    {
      title: 'S3 接收流量',
      metric: 'minio_s3_rx_rate',
      unit: 'byteps',
      color: '#2f6bff',
      icon: 'publish',
      compare: true,
      guide: [
        {
          label: 'S3 入向',
          detail: 'S3 接收流量速率，反映上传负载。'
        }
      ],
      footer: [
        { label: '发送', metric: 'minio_s3_tx_rate', unit: 'byteps' },
        { label: '等待', metric: 'minio_s3_waiting', unit: 'counts' }
      ]
    }
  ],
  charts: [
    {
      title: '空闲容量',
      subtitle: '可用逻辑空闲空间',
      metric: 'minio_usable_free',
      guide: [{ label: '空闲', detail: '纠删编码后的可用逻辑空闲容量。' }],
      series: [{ metric: 'minio_usable_free', label: '空闲容量', color: '#13c2c2', unit: 'bytes' }]
    },
    {
      title: '容量使用率',
      subtitle: '已用占可用总容量比例',
      metric: 'minio_usable_used_pct',
      guide: [{ label: '使用率', detail: '已用占可用总容量比例，接近 100% 需扩容。' }],
      series: [{ metric: 'minio_usable_used_pct', label: '使用率', color: '#ff8a1f', unit: 'percent' }]
    },
    {
      title: '冗余与成员',
      subtitle: '在线盘 / 节点 / 纠删组在线盘',
      metric: 'minio_drives_online',
      guide: [
        {
          label: '冗余',
          detail: '用在线盘、节点与纠删组在线盘观察集群冗余和成员健康。'
        }
      ],
      series: [
        { metric: 'minio_drives_online', label: '在线驱动器', color: '#27c274', unit: 'counts' },
        { metric: 'minio_nodes_online', label: '在线节点', color: '#597ef7', unit: 'counts' },
        { metric: 'minio_erasure_drives', label: '纠删组在线盘', color: '#8a5cff', unit: 'counts' }
      ]
    },
    {
      title: 'S3 流量',
      subtitle: '接收 / 发送',
      metric: 'minio_s3_rx_rate',
      guide: [
        { label: '流量', detail: 'S3 收发字节速率。' }
      ],
      series: [
        { metric: 'minio_s3_rx_rate', label: '接收', color: '#2f6bff', unit: 'byteps' },
        { metric: 'minio_s3_tx_rate', label: '发送', color: '#13c2c2', unit: 'byteps' }
      ]
    },
    {
      title: 'S3 请求队列',
      subtitle: '进行中 / 等待',
      metric: 'minio_s3_incoming',
      guide: [{ label: '请求', detail: '进行中与等待中的 S3 请求数。' }],
      series: [
        { metric: 'minio_s3_incoming', label: '进行中', color: '#27c274', unit: 'counts' },
        { metric: 'minio_s3_waiting', label: '等待', color: '#ff8a1f', unit: 'counts' }
      ]
    },
    {
      title: '鉴权拒绝',
      subtitle: '认证失败拒绝速率',
      metric: 'minio_s3_auth_reject_rate',
      guide: [{ label: '鉴权拒绝', detail: '因认证失败被拒绝的 S3 请求速率。' }],
      series: [
        { metric: 'minio_s3_auth_reject_rate', label: '鉴权拒绝', color: '#ff4d4f', unit: 'cps' }
      ]
    },
    {
      title: '服务端错误',
      subtitle: 'S3/API 5xx 错误速率',
      metric: 'minio_5xx_error_rate',
      guide: [{ label: '5xx 错误', detail: '服务端内部错误速率，持续大于零需检查 MinIO 日志与节点健康。' }],
      series: [{ metric: 'minio_5xx_error_rate', label: '5xx 错误', color: '#ff4d4f', unit: 'cps' }]
    }
  ],
  statusPanels: [],
  ringPanels: [],
  barPanels: [],
  details: []
};
