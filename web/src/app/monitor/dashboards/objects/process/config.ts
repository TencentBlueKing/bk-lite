import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';
import type { MetricEnumMap } from '../../shared/types';

/** 进程监控鲜活科技色板：高对比度、呼吸感强、与全局规范保持一致 */
const PROCESS_PALETTE = {
  emerald: '#10B981',   // 鲜亮翠绿 (存活状态、应用内存使用率)
  blue: '#2563EB',      // 活力皇家蓝 (进程 CPU 使用率)
  cyan: '#06B6D4',      // 清亮青蓝 (内存 RSS)
  indigo: '#6366F1',    // 现代紫靛 (线程数)
  amber: '#F59E0B',     // 暖金琥珀 (端口部分失活)
  orange: '#F97316',    // 活力暖橙 (打开文件数 FDs)
  rose: '#EF4444'       // 鲜明珊瑚红 (失活状态)
} as const;

const PROCESS_ALIVE_ENUM: MetricEnumMap = {
  0: { label: '失活', color: PROCESS_PALETTE.rose },
  1: { label: '存活', color: PROCESS_PALETTE.emerald }
};

const PROCESS_PORT_ALIVE_ENUM: MetricEnumMap = {
  0: { label: '失活', color: PROCESS_PALETTE.rose },
  0.5: { label: '部分失活', color: PROCESS_PALETTE.amber },
  1: { label: '存活', color: PROCESS_PALETTE.emerald }
};

export const PROCESS_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'process',
  pageTitle: '进程监控仪表盘',
  objectFallbackName: '进程',
  instanceType: 'process',
  collectionStatusQuery:
    "count({instance_type='process', collect_type='host', __$labels__}) by (instance_id, process_name)",
  metaItems: ['OS', 'process'],
  metrics: [
    {
      name: 'process_alive',
      display_name: '进程存活',
      description: '是否至少有一个匹配进程正在上报指标。',
      unit: 'none',
      query:
        'clamp_max(count(procstat_cpu_usage{instance_type="process", __$labels__}) by (instance_id, process_name), 1)',
      color: PROCESS_PALETTE.emerald
    },
    {
      name: 'process_port_alive',
      display_name: '端口存活',
      description: '已配置端口的存活状态：1=全部存活，0=全部失活，0.5=部分失活；无系列表示未采集端口。',
      unit: 'none',
      query:
        '((floor(((avg(clamp_max(net_response_result_code{instance_type="process", __$labels__}, 1) == bool 0) by (instance_id, process_name)) or process_port_alive{instance_type="process", __$labels__})) + ceil(((avg(clamp_max(net_response_result_code{instance_type="process", __$labels__}, 1) == bool 0) by (instance_id, process_name)) or process_port_alive{instance_type="process", __$labels__}))) / 2)',
      color: PROCESS_PALETTE.amber
    },
    {
      name: 'process_cpu_usage',
      display_name: '进程 CPU 使用率',
      description: '匹配进程的 CPU 使用率合计（按 process_name 聚合）。',
      unit: 'percent',
      query:
        'sum(procstat_cpu_usage{instance_type="process", __$labels__}) by (instance_id, process_name)',
      color: PROCESS_PALETTE.blue
    },
    {
      name: 'process_mem_usage',
      display_name: '应用内存使用率',
      description: '匹配进程相对系统内存的使用率合计（按 process_name 聚合）。',
      unit: 'percent',
      query:
        'sum(procstat_memory_usage{instance_type="process", __$labels__}) by (instance_id, process_name)',
      color: PROCESS_PALETTE.emerald
    },
    {
      name: 'process_memory_rss',
      display_name: '内存 RSS',
      description: '匹配进程常驻集大小合计（字节）。',
      unit: 'bytes',
      query:
        'sum(procstat_memory_rss{instance_type="process", __$labels__}) by (instance_id, process_name)',
      color: PROCESS_PALETTE.cyan
    },
    {
      name: 'process_num_threads',
      display_name: '线程数',
      description: '匹配进程的线程数合计。',
      unit: 'counts',
      query:
        'sum(procstat_num_threads{instance_type="process", __$labels__}) by (instance_id, process_name)',
      color: PROCESS_PALETTE.indigo
    },
    {
      name: 'process_num_fds',
      display_name: '打开文件数',
      description: '匹配进程打开的文件描述符数量合计；可能需要提升权限才能采集。',
      unit: 'counts',
      query:
        'sum(procstat_num_fds{instance_type="process", __$labels__}) by (instance_id, process_name)',
      color: PROCESS_PALETTE.orange
    }
  ],
  summaryCards: [
    {
      title: '进程存活',
      metric: 'process_alive',
      unit: 'none',
      color: PROCESS_PALETTE.emerald,
      icon: 'health',
      enumMap: PROCESS_ALIVE_ENUM,
      hideTrend: true,
      guide: [
        {
          label: '进程存活',
          detail: '至少有一个匹配进程正在上报 procstat 指标时为存活；无数据表示当前窗口未采到该进程。'
        }
      ]
    },
    {
      title: '端口存活',
      metric: 'process_port_alive',
      unit: 'none',
      color: PROCESS_PALETTE.amber,
      icon: 'api',
      enumMap: PROCESS_PORT_ALIVE_ENUM,
      // 端口探测为可选：未配置 ports 时无系列，隐藏卡片，避免误读为「存活」。
      hideWhenNoData: true,
      emptyValue: '未配置',
      hideTrend: true,
      guide: [
        {
          label: '端口存活',
          detail: '仅在采集配置了 ports 时展示。全部存活 / 部分失活 / 全部失活；未配置端口时不展示本卡片。'
        }
      ]
    },
    {
      title: 'CPU 使用率',
      metric: 'process_cpu_usage',
      unit: 'percent',
      color: PROCESS_PALETTE.blue,
      icon: 'thunder',
      compare: true,
      guide: [
        {
          label: '进程 CPU',
          detail: '匹配进程 CPU 使用率合计。持续偏高时对照线程数与主机 CPU，区分单进程打满与主机整体争用。'
        }
      ]
    },
    {
      title: '应用内存使用率',
      metric: 'process_mem_usage',
      unit: 'percent',
      color: PROCESS_PALETTE.emerald,
      icon: 'memory',
      compare: true,
      guide: [
        {
          label: '应用内存',
          detail: '相对系统内存的进程内存占比合计。可与下方 RSS 趋势对照判断绝对占用与相对压力。'
        }
      ],
      footer: [{ label: '内存 RSS', metric: 'process_memory_rss', unit: 'bytes' }]
    },
    {
      title: '线程数',
      metric: 'process_num_threads',
      unit: 'counts',
      color: PROCESS_PALETTE.indigo,
      icon: 'node',
      compare: true,
      guide: [
        {
          label: '线程数',
          detail: '匹配进程线程数合计。异常飙升可能伴随 CPU 争用或线程泄漏。'
        }
      ],
      footer: [{ label: '打开文件数', metric: 'process_num_fds', unit: 'counts' }]
    }
  ],
  charts: [
    {
      title: '资源使用趋势',
      subtitle: 'CPU 与应用内存',
      metric: 'process_cpu_usage',
      guide: [
        {
          label: '资源使用',
          detail: '对比进程 CPU 使用率与应用内存使用率随时间的变化。'
        }
      ],
      series: [
        { metric: 'process_cpu_usage', label: 'CPU 使用率', color: PROCESS_PALETTE.blue, unit: 'percent' },
        { metric: 'process_mem_usage', label: '应用内存使用率', color: PROCESS_PALETTE.emerald, unit: 'percent' }
      ]
    },
    {
      title: '内存 RSS 趋势',
      subtitle: '常驻物理内存',
      metric: 'process_memory_rss',
      guide: [
        {
          label: '内存 RSS',
          detail: '进程常驻物理内存合计。持续抬升需关注泄漏或缓存膨胀。'
        }
      ],
      series: [
        { metric: 'process_memory_rss', label: '内存 RSS', color: PROCESS_PALETTE.cyan, unit: 'bytes' }
      ]
    },
    {
      title: '线程数趋势',
      subtitle: '并发线程规模',
      metric: 'process_num_threads',
      guide: [
        {
          label: '线程数',
          detail: '匹配进程线程数合计。异常飙升可能伴随 CPU 争用或线程泄漏。'
        }
      ],
      series: [
        { metric: 'process_num_threads', label: '线程数', color: PROCESS_PALETTE.indigo, unit: 'counts' }
      ]
    },
    {
      title: '打开文件数趋势',
      subtitle: '文件句柄 (FDs)',
      metric: 'process_num_fds',
      guide: [
        {
          label: '打开文件数',
          detail: '打开的文件描述符数量合计。持续逼近 ulimit 时优先排查泄漏；无数据时检查采集权限。'
        }
      ],
      series: [
        { metric: 'process_num_fds', label: '打开文件数', color: PROCESS_PALETTE.orange, unit: 'counts' }
      ]
    }
  ],
  ringPanels: [],
  barPanels: [],
  details: []
};
