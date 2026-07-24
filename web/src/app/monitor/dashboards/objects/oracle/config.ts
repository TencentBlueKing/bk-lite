import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';
export const ORACLE_DASHBOARD_CONFIG: SimpleDashboardConfig = { routeKey: 'oracle', pageTitle: 'Oracle 监控仪表盘', objectFallbackName: 'Oracle', instanceType: 'oracle', collectionStatusQuery: "count({instance_type='oracle', collect_type='exporter', __$labels__}) by (instance_id)", metaItems: ['Oracle-Exporter', 'exporter'], metrics: [
  { name: 'oracle_up', display_name: '实例状态', description: 'Oracle exporter 的实例可用性。', unit: 'none', query: 'oracledb_up_gauge{__$labels__}', color: '#27c274' },
  { name: 'oracle_sessions', display_name: '会话数', description: '当前 Oracle 会话数。', unit: 'counts', query: 'oracledb_sessions_value_gauge{__$labels__}', color: '#2f6bff' },
  { name: 'oracle_tablespace', display_name: '表空间使用率', description: '表空间已用容量比例。', unit: 'percent', query: 'max(oracledb_tablespace_used_percent_gauge{__$labels__})', color: '#ff8a1f' },
  { name: 'oracle_user_io', display_name: '用户 I/O 等待', description: '用户 I/O 等待时间。', unit: 'ms', query: 'oracledb_wait_time_user_io_gauge{__$labels__}', color: '#ff4d4f' },
  { name: 'oracle_sga', display_name: 'SGA 使用率', description: '共享全局区使用率。', unit: 'percent', query: 'oracledb_sga_used_percent_gauge{__$labels__}', color: '#8a5cff' },
], summaryCards: [
  { title: '实例状态', metric: 'oracle_up', color: '#27c274', icon: 'health', guide: [{ label: '实例状态', detail: '不可用时优先检查数据库实例与 exporter 连接。' }] },
  { title: '会话数', metric: 'oracle_sessions', color: '#2f6bff', icon: 'node', guide: [{ label: '会话压力', detail: '持续升高可能表示连接池或业务并发压力。' }] },
  { title: '表空间使用率', metric: 'oracle_tablespace', color: '#ff8a1f', icon: 'database', compare: true, compareFavorableDirection: 'down', guide: [{ label: '容量风险', detail: '接近容量上限前应扩容或清理表空间。' }] },
  { title: '用户 I/O 等待', metric: 'oracle_user_io', color: '#ff4d4f', icon: 'clock', compare: true, compareFavorableDirection: 'down', guide: [{ label: 'I/O 等待', detail: '持续升高时排查存储与 SQL 访问模式。' }] },
], charts: [
  { title: '容量与内存趋势', subtitle: '表空间与 SGA 使用率', metric: 'oracle_tablespace', guide: [{ label: '容量与内存', detail: '并列观察表空间容量和 SGA 内存压力。' }], series: [{ metric: 'oracle_tablespace', label: '表空间使用率', color: '#ff8a1f', unit: 'percent' }, { metric: 'oracle_sga', label: 'SGA 使用率', color: '#8a5cff', unit: 'percent' }] },
  { title: '会话与 I/O 等待', subtitle: '会话数、用户 I/O 等待', metric: 'oracle_sessions', guide: [{ label: '负载关联', detail: '会话增长伴随 I/O 等待上升时，需定位高负载 SQL。' }], series: [{ metric: 'oracle_sessions', label: '会话数', color: '#2f6bff', unit: 'counts' }, { metric: 'oracle_user_io', label: '用户 I/O 等待', color: '#ff4d4f', unit: 'ms' }] },
], details: [{ title: '实例诊断', subtitle: '数据库容量与会话压力', rows: [{ label: '会话数', metric: 'oracle_sessions', unit: 'counts' }, { label: '表空间使用率', metric: 'oracle_tablespace', unit: 'percent', tone: 'warning' }, { label: '用户 I/O 等待', metric: 'oracle_user_io', unit: 'ms', tone: 'error' }] }] };
