import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

const STORAGE_LABELS = "{instance_type='storage', __$labels__}";
const PURE_LABELS = "{instance_type='storage', resource_type='pure', __$labels__}";
const INFINIBOX_LABELS = "{instance_type='storage', resource_type='infinibox', __$labels__}";

export const STORAGE_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'storage',
  pageTitle: '存储监控仪表盘',
  objectFallbackName: 'Storage',
  instanceType: 'storage',
  collectionStatusQuery: `count(${STORAGE_LABELS}) by (instance_id)`,
  metaItems: ['Storage', 'Pure / InfiniBox'],
  metrics: [
    {
      name: 'storage_capacity_total_bytes',
      display_name: '总容量',
      description: '存储阵列或存储池可用总容量。Pure 取阵列总容量，InfiniBox 取 pool 物理容量汇总。',
      unit: 'bytes',
      query:
        `sum(pure_array_capacity_bytes_gauge${PURE_LABELS}) by (instance_id) or ` +
        `sum(infinibox_pool_physical_capacity_bytes_gauge${INFINIBOX_LABELS}) by (instance_id)`,
      color: '#2f6bff'
    },
    {
      name: 'storage_capacity_used_bytes',
      display_name: '已用容量',
      description: '存储阵列或存储池已分配/已使用容量。',
      unit: 'bytes',
      query:
        `sum(pure_array_used_bytes_gauge${PURE_LABELS}) by (instance_id) or ` +
        `sum(infinibox_pool_allocated_physical_bytes_gauge${INFINIBOX_LABELS}) by (instance_id)`,
      color: '#ff8a1f'
    },
    {
      name: 'storage_capacity_free_bytes',
      display_name: '可用容量',
      description: '存储阵列或存储池剩余可用容量。',
      unit: 'bytes',
      query:
        `(sum(pure_array_capacity_bytes_gauge${PURE_LABELS}) by (instance_id) - sum(pure_array_used_bytes_gauge${PURE_LABELS}) by (instance_id)) or ` +
        `sum(infinibox_pool_free_physical_bytes_gauge${INFINIBOX_LABELS}) by (instance_id)`,
      color: '#27c274'
    },
    {
      name: 'storage_capacity_used_percent',
      display_name: '容量使用率',
      description: '已用容量占总容量比例。Pure 使用阵列已用/总容量，InfiniBox 使用 pool 已分配物理容量/物理容量。',
      unit: 'percent',
      query:
        `(sum(pure_array_used_bytes_gauge${PURE_LABELS}) by (instance_id) / sum(pure_array_capacity_bytes_gauge${PURE_LABELS}) by (instance_id) * 100) or ` +
        `(sum(infinibox_pool_allocated_physical_bytes_gauge${INFINIBOX_LABELS}) by (instance_id) / sum(infinibox_pool_physical_capacity_bytes_gauge${INFINIBOX_LABELS}) by (instance_id) * 100)`,
      color: '#faad14'
    },
    {
      name: 'storage_read_iops',
      display_name: '读 IOPS',
      description: '阵列或卷维度读 IOPS。Pure 取阵列读 IOPS，InfiniBox 汇总 volume 读 IOPS。',
      unit: 'counts',
      query:
        `sum(pure_array_read_iops_gauge${PURE_LABELS}) by (instance_id) or ` +
        `sum(infinibox_volume_read_iops_gauge${INFINIBOX_LABELS}) by (instance_id)`,
      color: '#2f6bff'
    },
    {
      name: 'storage_write_iops',
      display_name: '写 IOPS',
      description: '阵列或卷维度写 IOPS。Pure 取阵列写 IOPS，InfiniBox 汇总 volume 写 IOPS。',
      unit: 'counts',
      query:
        `sum(pure_array_write_iops_gauge${PURE_LABELS}) by (instance_id) or ` +
        `sum(infinibox_volume_write_iops_gauge${INFINIBOX_LABELS}) by (instance_id)`,
      color: '#13c2c2'
    },
    {
      name: 'storage_read_bandwidth',
      display_name: '读吞吐',
      description: '阵列或卷维度读吞吐速率。',
      unit: 'byteps',
      query:
        `sum(pure_array_read_bandwidth_gauge${PURE_LABELS}) by (instance_id) or ` +
        `sum(infinibox_volume_read_bandwidth_gauge${INFINIBOX_LABELS}) by (instance_id)`,
      color: '#27c274'
    },
    {
      name: 'storage_write_bandwidth',
      display_name: '写吞吐',
      description: '阵列或卷维度写吞吐速率。',
      unit: 'byteps',
      query:
        `sum(pure_array_write_bandwidth_gauge${PURE_LABELS}) by (instance_id) or ` +
        `sum(infinibox_volume_write_bandwidth_gauge${INFINIBOX_LABELS}) by (instance_id)`,
      color: '#9254de'
    },
    {
      name: 'storage_read_latency',
      display_name: '读延迟',
      description: '读请求平均延迟，单位毫秒。',
      unit: 'ms',
      query:
        `avg(pure_array_read_latency_gauge${PURE_LABELS}) by (instance_id) or ` +
        `avg(infinibox_volume_read_latency_gauge${INFINIBOX_LABELS}) by (instance_id)`,
      color: '#ff4d4f'
    },
    {
      name: 'storage_write_latency',
      display_name: '写延迟',
      description: '写请求平均延迟，单位毫秒。',
      unit: 'ms',
      query:
        `avg(pure_array_write_latency_gauge${PURE_LABELS}) by (instance_id) or ` +
        `avg(infinibox_volume_write_latency_gauge${INFINIBOX_LABELS}) by (instance_id)`,
      color: '#fa8c16'
    },
    {
      name: 'storage_volume_count',
      display_name: '卷数量',
      description: '当前阵列或存储池中的卷数量。',
      unit: 'counts',
      query:
        `max(pure_volume_count_gauge${PURE_LABELS}) by (instance_id) or ` +
        `max(infinibox_volume_count_gauge${INFINIBOX_LABELS}) by (instance_id)`,
      color: '#597ef7'
    },
    {
      name: 'storage_pool_count',
      display_name: 'Pool 数量',
      description: 'InfiniBox pool 数量。Pure FlashArray 无 pool 指标时自动为空。',
      unit: 'counts',
      query: `max(infinibox_pool_count_gauge${INFINIBOX_LABELS}) by (instance_id)`,
      color: '#08979c'
    },
    {
      name: 'storage_data_reduction',
      display_name: '数据缩减率',
      description: 'Pure FlashArray 数据缩减率。非 Pure 阵列没有该指标时自动为空。',
      unit: 'counts',
      query: `avg(pure_array_data_reduction_gauge${PURE_LABELS}) by (instance_id)`,
      color: '#722ed1'
    },
    {
      name: 'storage_virtual_capacity_bytes',
      display_name: '虚拟容量',
      description: 'InfiniBox pool 虚拟容量汇总。非 InfiniBox 阵列没有该指标时自动为空。',
      unit: 'bytes',
      query: `sum(infinibox_pool_virtual_capacity_bytes_gauge${INFINIBOX_LABELS}) by (instance_id)`,
      color: '#13c2c2'
    },
    {
      name: 'storage_virtual_allocated_bytes',
      display_name: '虚拟已分配',
      description: 'InfiniBox pool 虚拟已分配容量汇总。',
      unit: 'bytes',
      query: `sum(infinibox_pool_allocated_virtual_bytes_gauge${INFINIBOX_LABELS}) by (instance_id)`,
      color: '#f759ab'
    },
    {
      name: 'storage_volume_read_iops_by_volume',
      display_name: '卷读 IOPS',
      description: '卷维度读 IOPS，用于后续资源 TopN 和卷级诊断。Pure 使用 pure_volume_read_iops_gauge，InfiniBox 使用 infinibox_volume_read_iops_gauge。',
      unit: 'counts',
      query:
        `sum(pure_volume_read_iops_gauge${PURE_LABELS}) by (instance_id, volume) or ` +
        `sum(infinibox_volume_read_iops_gauge${INFINIBOX_LABELS}) by (instance_id, volume)`,
      color: '#2f6bff'
    }
  ],
  summaryCards: [
    {
      title: '容量使用率',
      metric: 'storage_capacity_used_percent',
      unit: 'percent',
      color: '#faad14',
      icon: 'database',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '容量使用率', detail: '已用容量占总容量比例；持续升高说明需要扩容或清理。' }],
      footer: [{ label: '已用', metric: 'storage_capacity_used_bytes', unit: 'bytes' }]
    },
    {
      title: '总容量',
      metric: 'storage_capacity_total_bytes',
      unit: 'bytes',
      color: '#2f6bff',
      icon: 'database',
      hideTrend: true,
      guide: [{ label: '总容量', detail: '阵列或 pool 的可用总容量。' }],
      footer: [{ label: '可用', metric: 'storage_capacity_free_bytes', unit: 'bytes' }]
    },
    {
      title: '读 IOPS',
      metric: 'storage_read_iops',
      unit: 'counts',
      color: '#2f6bff',
      icon: 'thunder',
      guide: [{ label: '读 IOPS', detail: '读请求吞吐能力，突增常对应业务读压力。' }],
      footer: [{ label: '写', metric: 'storage_write_iops', unit: 'counts' }]
    },
    {
      title: '读吞吐',
      metric: 'storage_read_bandwidth',
      unit: 'byteps',
      color: '#27c274',
      icon: 'api',
      guide: [{ label: '读吞吐', detail: '读方向吞吐速率。' }],
      footer: [{ label: '写', metric: 'storage_write_bandwidth', unit: 'byteps' }]
    },
    {
      title: '读延迟',
      metric: 'storage_read_latency',
      unit: 'ms',
      color: '#ff4d4f',
      icon: 'health',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '读延迟', detail: '读请求平均响应时间；升高会直接影响业务体验。' }],
      footer: [{ label: '写延迟', metric: 'storage_write_latency', unit: 'ms' }]
    }
  ],
  charts: [
    {
      title: 'IOPS 趋势',
      subtitle: '读写请求速率',
      metric: 'storage_read_iops',
      guide: [{ label: 'IOPS', detail: '观察读写请求压力的趋势和峰值。' }],
      series: [
        { metric: 'storage_read_iops', label: '读 IOPS', color: '#2f6bff', unit: 'counts' },
        { metric: 'storage_write_iops', label: '写 IOPS', color: '#13c2c2', unit: 'counts' }
      ]
    },
    {
      title: '吞吐趋势',
      subtitle: '读写带宽',
      metric: 'storage_read_bandwidth',
      guide: [{ label: '吞吐', detail: '观察读写方向的带宽变化。' }],
      series: [
        { metric: 'storage_read_bandwidth', label: '读吞吐', color: '#27c274', unit: 'byteps' },
        { metric: 'storage_write_bandwidth', label: '写吞吐', color: '#9254de', unit: 'byteps' }
      ]
    },
    {
      title: '延迟趋势',
      subtitle: '读写响应时间',
      metric: 'storage_read_latency',
      guide: [{ label: '延迟', detail: '持续升高通常表示阵列压力、后端介质或网络路径存在瓶颈。' }],
      series: [
        { metric: 'storage_read_latency', label: '读延迟', color: '#ff4d4f', unit: 'ms' },
        { metric: 'storage_write_latency', label: '写延迟', color: '#fa8c16', unit: 'ms' }
      ]
    }
  ],
  ringPanels: [
    {
      title: '容量分布',
      subtitle: '已用与可用容量',
      centerMetric: 'storage_capacity_used_percent',
      centerCaption: '使用率',
      centerUnit: 'percent',
      guide: [{ label: '容量分布', detail: '展示当前已用容量和剩余容量，帮助快速判断扩容风险。' }],
      segments: [
        { label: '已用', metric: 'storage_capacity_used_bytes', color: '#ff8a1f', unit: 'bytes' },
        { label: '可用', metric: 'storage_capacity_free_bytes', color: '#27c274', unit: 'bytes' }
      ]
    }
  ],
  barPanels: [
    {
      title: '资源规模',
      subtitle: '卷与 pool 数量',
      guide: [{ label: '资源规模', detail: '展示当前采集到的核心资源数量。Pure 可能没有 pool 数量。' }],
      items: [
        { label: '卷数量', metric: 'storage_volume_count', color: '#597ef7', unit: 'counts' },
        { label: 'Pool 数量', metric: 'storage_pool_count', color: '#08979c', unit: 'counts' }
      ]
    },
    {
      title: '厂商扩展',
      subtitle: 'Pure / InfiniBox 差异化能力',
      guide: [{ label: '厂商扩展', detail: 'Pure 展示数据缩减率，InfiniBox 展示虚拟容量和虚拟已分配。' }],
      items: [
        { label: '数据缩减率', metric: 'storage_data_reduction', color: '#722ed1', unit: 'counts' },
        { label: '虚拟容量', metric: 'storage_virtual_capacity_bytes', color: '#13c2c2', unit: 'bytes' },
        { label: '虚拟已分配', metric: 'storage_virtual_allocated_bytes', color: '#f759ab', unit: 'bytes' }
      ]
    }
  ],
  details: [
    {
      title: '容量诊断',
      subtitle: '容量、使用率和资源规模',
      rows: [
        { label: '容量使用率', metric: 'storage_capacity_used_percent', unit: 'percent', tone: 'warning' },
        { label: '已用容量', metric: 'storage_capacity_used_bytes', unit: 'bytes' },
        { label: '可用容量', metric: 'storage_capacity_free_bytes', unit: 'bytes' },
        { label: '卷数量', metric: 'storage_volume_count', unit: 'counts' },
        { label: 'Pool 数量', metric: 'storage_pool_count', unit: 'counts' }
      ]
    },
    {
      title: '性能诊断',
      subtitle: 'IOPS、吞吐和延迟',
      rows: [
        { label: '读 IOPS', metric: 'storage_read_iops', unit: 'counts' },
        { label: '写 IOPS', metric: 'storage_write_iops', unit: 'counts' },
        { label: '读吞吐', metric: 'storage_read_bandwidth', unit: 'byteps' },
        { label: '写吞吐', metric: 'storage_write_bandwidth', unit: 'byteps' },
        { label: '读延迟', metric: 'storage_read_latency', unit: 'ms', tone: 'warning' },
        { label: '写延迟', metric: 'storage_write_latency', unit: 'ms', tone: 'warning' }
      ]
    }
  ]
};
