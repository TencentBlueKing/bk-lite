import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

/** Oracle 监控高对比鲜活科技色板 */
const ORACLE_PALETTE = {
  emerald: '#10B981',   // 正常状态、提交速率
  blue: '#2563EB',      // 运行时长、会话数、SQL执行、SGA使用
  cyan: '#06B6D4',      // PGA使用、网络等待
  indigo: '#6366F1',    // 进程数、SQL解析、应用等待
  amber: '#F59E0B',     // 资源限制使用率、System I/O 等待
  orange: '#F97316',    // User I/O 等待
  rose: '#EF4444'       // 异常状态、表空间使用率、回滚、并发等待
} as const;

const ORACLE_UP_ENUM = {
  1: { label: '正常', color: ORACLE_PALETTE.emerald },
  0: { label: '异常', color: ORACLE_PALETTE.rose }
};

export const ORACLE_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'oracle',
  pageTitle: 'Oracle 监控仪表盘',
  objectFallbackName: 'Oracle',
  instanceType: 'oracle',
  collectionStatusQuery:
    "count({instance_type='oracle', collect_type='exporter', __$labels__}) by (instance_id)",
  metaItems: ['Oracle-Exporter', 'database', 'Wait Class'],
  metrics: [
    {
      name: 'oracledb_up',
      display_name: '数据库状态',
      description: 'Oracle 实例可达性：1 正常、0 异常。',
      unit: 'none',
      query: 'max by (instance_id) (oracledb_up_gauge{__$labels__})',
      color: ORACLE_PALETTE.emerald
    },
    {
      name: 'oracledb_uptime',
      display_name: '实例运行时长',
      description: 'Oracle 实例已运行时长。',
      unit: 's',
      query: 'max by (instance_id) (oracledb_uptime_seconds_gauge{__$labels__})',
      color: ORACLE_PALETTE.blue
    },
    {
      name: 'oracledb_sessions',
      display_name: '会话数',
      description: '当前打开会话总数（按 status/type 汇总）。',
      unit: 'counts',
      query: 'sum by (instance_id) (oracledb_sessions_value_gauge{__$labels__})',
      color: ORACLE_PALETTE.blue
    },
    {
      name: 'oracledb_processes',
      display_name: '进程数',
      description: '当前活跃数据库进程数。',
      unit: 'counts',
      query: 'max by (instance_id) (oracledb_process_count_gauge{__$labels__})',
      color: ORACLE_PALETTE.indigo
    },
    {
      name: 'oracledb_resource_util_max',
      display_name: '资源使用率峰值',
      description: '各资源限制使用率的最大值（sessions/processes/memory 等）。',
      unit: 'percent',
      query:
        'max by (instance_id) (clamp_min(oracledb_resource_current_utilization_gauge{__$labels__} / clamp_min(oracledb_resource_limit_value_gauge{__$labels__}, 1) * 100, 0))',
      color: ORACLE_PALETTE.amber
    },
    {
      name: 'oracledb_tablespace_used_max',
      display_name: '最忙表空间使用率',
      description: '所有表空间中使用率最高的值。',
      unit: 'percent',
      query: 'max by (instance_id) (oracledb_tablespace_used_percent_gauge{__$labels__})',
      color: ORACLE_PALETTE.rose
    },
    {
      name: 'oracledb_execute_rate',
      display_name: 'SQL 执行速率',
      description: 'SQL 执行速率，反映库负载。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(oracledb_activity_execute_count_gauge{__$labels__}[__$window__]))',
      color: ORACLE_PALETTE.blue
    },
    {
      name: 'oracledb_parse_rate',
      display_name: 'SQL 解析速率',
      description: 'SQL 解析速率，升高可能意味着硬解析偏多。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(oracledb_activity_parse_count_total_gauge{__$labels__}[__$window__]))',
      color: ORACLE_PALETTE.indigo
    },
    {
      name: 'oracledb_commit_rate',
      display_name: '提交速率',
      description: '用户事务提交速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(oracledb_activity_user_commits_gauge{__$labels__}[__$window__]))',
      color: ORACLE_PALETTE.emerald
    },
    {
      name: 'oracledb_rollback_rate',
      display_name: '回滚速率',
      description: '用户事务回滚速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(oracledb_activity_user_rollbacks_gauge{__$labels__}[__$window__]))',
      color: ORACLE_PALETTE.rose
    },
    {
      name: 'oracledb_wait_user_io',
      display_name: 'User I/O 等待',
      description: '用户 I/O 等待时间。',
      unit: 'ms',
      query: 'max by (instance_id) (oracledb_wait_time_user_io_gauge{__$labels__})',
      color: ORACLE_PALETTE.orange
    },
    {
      name: 'oracledb_wait_system_io',
      display_name: 'System I/O 等待',
      description: '系统 I/O 等待时间。',
      unit: 'ms',
      query: 'max by (instance_id) (oracledb_wait_time_system_io_gauge{__$labels__})',
      color: ORACLE_PALETTE.amber
    },
    {
      name: 'oracledb_wait_concurrency',
      display_name: '并发等待',
      description: '锁/资源争用等待时间。',
      unit: 'ms',
      query: 'max by (instance_id) (oracledb_wait_time_concurrency_gauge{__$labels__})',
      color: ORACLE_PALETTE.rose
    },
    {
      name: 'oracledb_wait_commit',
      display_name: '提交等待',
      description: '事务提交等待时间。',
      unit: 'ms',
      query: 'max by (instance_id) (oracledb_wait_time_commit_gauge{__$labels__})',
      color: ORACLE_PALETTE.emerald
    },
    {
      name: 'oracledb_wait_application',
      display_name: '应用等待',
      description: '应用/客户端侧等待时间。',
      unit: 'ms',
      query: 'max by (instance_id) (oracledb_wait_time_application_gauge{__$labels__})',
      color: ORACLE_PALETTE.indigo
    },
    {
      name: 'oracledb_wait_network',
      display_name: '网络等待',
      description: '网络传输等待时间。',
      unit: 'ms',
      query: 'max by (instance_id) (oracledb_wait_time_network_gauge{__$labels__})',
      color: ORACLE_PALETTE.cyan
    },
    {
      name: 'oracledb_sga_used_pct',
      display_name: 'SGA 使用率',
      description: 'SGA 内存使用百分比。',
      unit: 'percent',
      query: 'max by (instance_id) (oracledb_sga_used_percent_gauge{__$labels__})',
      color: ORACLE_PALETTE.blue
    },
    {
      name: 'oracledb_pga_used_pct',
      display_name: 'PGA 使用率',
      description: 'PGA 内存使用百分比。',
      unit: 'percent',
      query: 'max by (instance_id) (oracledb_pga_used_percent_gauge{__$labels__})',
      color: ORACLE_PALETTE.cyan
    },
    {
      name: 'oracledb_sga_total',
      display_name: 'SGA 总量',
      description: 'SGA 总大小。',
      unit: 'bytes',
      query: 'max by (instance_id) (oracledb_sga_total_gauge{__$labels__})',
      color: ORACLE_PALETTE.blue
    },
    {
      name: 'oracledb_pga_total',
      display_name: 'PGA 总量',
      description: 'PGA 总大小。',
      unit: 'bytes',
      query: 'max by (instance_id) (oracledb_pga_total_gauge{__$labels__})',
      color: ORACLE_PALETTE.cyan
    }
  ],
  summaryCards: [
    {
      title: '数据库状态',
      metric: 'oracledb_up',
      color: ORACLE_PALETTE.emerald,
      icon: 'health',
      enumMap: ORACLE_UP_ENUM,
      guide: [
        {
          label: '数据库状态',
          detail: 'Oracle 实例可达性：正常表示 exporter 能连上库；异常时先区分库宕与采集失败。'
        }
      ],
      footer: [{ label: '运行时长', metric: 'oracledb_uptime', formatter: 'duration' }]
    },
    {
      title: '会话数',
      metric: 'oracledb_sessions',
      unit: 'counts',
      color: ORACLE_PALETTE.blue,
      icon: 'node',
      compare: true,
      guide: [
        {
          label: '会话数',
          detail: '当前打开会话总数。持续抬升需对照资源使用率与进程数，排查会话泄漏或连接池过大。'
        }
      ],
      footer: [{ label: '进程数', metric: 'oracledb_processes', unit: 'counts' }]
    },
    {
      title: 'User I/O 等待',
      metric: 'oracledb_wait_user_io',
      unit: 'ms',
      color: ORACLE_PALETTE.orange,
      icon: 'clock',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: 'User I/O',
          detail: '用户 I/O 等待时间，是 Oracle 性能诊断的核心 Wait Class 之一；升高常指向慢盘或低效 SQL。'
        }
      ]
    }
  ],
  charts: [
    {
      title: 'SQL 活性',
      subtitle: '执行与解析速率',
      metric: 'oracledb_execute_rate',
      guide: [
        { label: '执行速率', detail: 'SQL 执行速率，反映库负载变化。' },
        { label: '解析速率', detail: 'SQL 解析速率，相对执行偏高时关注硬解析与游标共享。' }
      ],
      series: [
        { metric: 'oracledb_execute_rate', label: '执行', color: ORACLE_PALETTE.blue, unit: 'cps' },
        { metric: 'oracledb_parse_rate', label: '解析', color: ORACLE_PALETTE.indigo, unit: 'cps' }
      ]
    },
    {
      title: '事务提交与回滚',
      subtitle: '提交 / 回滚速率',
      metric: 'oracledb_commit_rate',
      guide: [
        { label: '提交', detail: '用户事务提交速率。' },
        { label: '回滚', detail: '用户事务回滚速率；相对提交异常升高需排查失败事务。' }
      ],
      series: [
        { metric: 'oracledb_commit_rate', label: '提交', color: ORACLE_PALETTE.emerald, unit: 'cps' },
        { metric: 'oracledb_rollback_rate', label: '回滚', color: ORACLE_PALETTE.rose, unit: 'cps' }
      ]
    },
    {
      title: 'Wait Class 概览',
      subtitle: 'User I/O / System I/O / 并发 / 提交',
      metric: 'oracledb_wait_user_io',
      guide: [
        {
          label: 'Wait Class',
          detail: 'Oracle 典型等待类时间。User I/O 与并发等待抬升是常见性能瓶颈信号。'
        }
      ],
      series: [
        { metric: 'oracledb_wait_user_io', label: 'User I/O', color: ORACLE_PALETTE.orange, unit: 'ms' },
        { metric: 'oracledb_wait_system_io', label: 'System I/O', color: ORACLE_PALETTE.amber, unit: 'ms' },
        { metric: 'oracledb_wait_concurrency', label: '并发等待', color: ORACLE_PALETTE.rose, unit: 'ms' },
        { metric: 'oracledb_wait_commit', label: '提交等待', color: ORACLE_PALETTE.emerald, unit: 'ms' }
      ]
    },
    {
      title: '内存使用',
      subtitle: 'SGA 与 PGA 使用率',
      metric: 'oracledb_sga_used_pct',
      guide: [
        { label: 'SGA', detail: '系统全局区内存使用百分比。' },
        { label: 'PGA', detail: '程序全局区内存使用百分比。' }
      ],
      series: [
        { metric: 'oracledb_sga_used_pct', label: 'SGA 使用率', color: ORACLE_PALETTE.blue, unit: 'percent' },
        { metric: 'oracledb_pga_used_pct', label: 'PGA 使用率', color: ORACLE_PALETTE.cyan, unit: 'percent' }
      ]
    }
  ],
  ringPanels: [],
  barPanels: [],
  details: []
};
