import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

// 实例盘 KPI 主答「本机角色」；集群是否具备主节点只作 footer，避免「选举/已选举」叠词。
const HAS_LEADER_ENUM = {
  1: { label: '主节点在线', color: '#27c274' },
  0: { label: '主节点缺失', color: '#ff4d4f' }
};

const IS_LEADER_ENUM = {
  1: { label: '主节点', color: '#27c274' },
  0: { label: '从节点', color: '#8c8c8c' }
};

/**
 * Etcd 专业盘：Raft 可用性 + 后端配额/碎片 + WAL/backend 磁盘时延 + 提案积压。
 * 不是 HTTP 中间件 QPS 模板。
 */
export const ETCD_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'etcd',
  pageTitle: 'Etcd 监控仪表盘',
  objectFallbackName: 'Etcd',
  instanceType: 'etcd',
  collectionStatusQuery:
    "count({instance_type='etcd', collect_type='bkpull', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'bkpull', 'Raft'],
  metrics: [
    {
      name: 'etcd_has_leader',
      display_name: '集群主节点',
      description: '集群是否具备可用的主节点。',
      unit: 'none',
      query: 'max by (instance_id) (etcd_server_has_leader_gauge{__$labels__})',
      color: '#27c274'
    },
    {
      name: 'etcd_is_leader',
      display_name: '本机角色',
      description: '当前实例是主节点还是从节点。',
      unit: 'none',
      query: 'max by (instance_id) (etcd_server_is_leader_gauge{__$labels__})',
      color: '#2f6bff'
    },
    {
      name: 'etcd_backend_usage_pct',
      display_name: '后端存储使用率',
      description: '后端已分配空间占总配额的比例。',
      unit: 'percent',
      query:
        'clamp_min(etcd_mvcc_db_total_size_in_bytes_gauge{__$labels__} / clamp_min(etcd_server_quota_backend_bytes_gauge{__$labels__}, 1) * 100, 0)',
      color: '#ff8a1f'
    },
    {
      name: 'etcd_proposals_pending',
      display_name: '提案积压',
      description: '待处理提案数。',
      unit: 'counts',
      query: 'max by (instance_id) (etcd_server_proposals_pending_gauge{__$labels__})',
      color: '#ff4d4f'
    },
    {
      name: 'etcd_wal_fsync_p99',
      display_name: 'WAL fsync P99',
      description: 'WAL 刷盘延迟 P99。',
      unit: 's',
      query:
        'histogram_quantile(0.99, sum(rate((label_replace({__name__=~"etcd_disk_wal_fsync_duration_seconds_[0-9.]+", __$labels__}, "le", "$1", "__name__", "etcd_disk_wal_fsync_duration_seconds_(.+)"))[5m:]) or label_replace(rate(etcd_disk_wal_fsync_duration_seconds_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (instance_id, le))',
      color: '#722ed1'
    },
    {
      name: 'etcd_backend_commit_p99',
      display_name: 'Backend commit P99',
      description: '后端 commit 延迟 P99。',
      unit: 's',
      query:
        'histogram_quantile(0.99, sum(rate((label_replace({__name__=~"etcd_disk_backend_commit_duration_seconds_[0-9.]+", __$labels__}, "le", "$1", "__name__", "etcd_disk_backend_commit_duration_seconds_(.+)"))[5m:]) or label_replace(rate(etcd_disk_backend_commit_duration_seconds_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (instance_id, le))',
      color: '#8a5cff'
    },
    {
      name: 'etcd_active_peers',
      display_name: '活跃节点连接',
      description: '可用的节点间连接数。',
      unit: 'counts',
      query: 'sum by (instance_id) (etcd_network_active_peers_gauge{__$labels__})',
      color: '#13c2c2'
    },
    {
      name: 'etcd_leader_changes_rate',
      display_name: '主节点切换频率',
      description: '主节点切换速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(etcd_server_leader_changes_seen_total_counter{__$labels__}[__$window__]))',
      color: '#ff8a1f'
    },
    {
      name: 'etcd_heartbeat_fail_rate',
      display_name: '心跳失败频率',
      description: '心跳发送失败速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(etcd_server_heartbeat_send_failures_total_counter{__$labels__}[__$window__]))',
      color: '#ff4d4f'
    },
    {
      name: 'etcd_apply_lag',
      display_name: '提案应用滞后',
      description: '已提交但未应用的提案数。',
      unit: 'counts',
      query:
        'clamp_min(etcd_server_proposals_committed_total_gauge{__$labels__} - etcd_server_proposals_applied_total_gauge{__$labels__}, 0)',
      color: '#faad14'
    },
    {
      name: 'etcd_proposals_failed_rate',
      display_name: '提案失败速率',
      description: '提案失败速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(etcd_server_proposals_failed_total_counter{__$labels__}[__$window__]))',
      color: '#ff4d4f'
    },
    {
      name: 'etcd_proposals_committed_rate',
      display_name: '提案提交速率',
      description: '提案提交速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(etcd_server_proposals_committed_total_gauge{__$labels__}[__$window__]))',
      color: '#27c274'
    },
    {
      name: 'etcd_proposals_applied_rate',
      display_name: '提案应用速率',
      description: '提案应用速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(etcd_server_proposals_applied_total_gauge{__$labels__}[__$window__]))',
      color: '#2f6bff'
    },
    {
      name: 'etcd_backend_remaining',
      display_name: '后端剩余容量',
      description: '距离配额上限的剩余空间。',
      unit: 'bytes',
      query:
        'clamp_min(etcd_server_quota_backend_bytes_gauge{__$labels__} - etcd_mvcc_db_total_size_in_bytes_gauge{__$labels__}, 0)',
      color: '#13c2c2'
    },
    {
      name: 'etcd_fragmentation_pct',
      display_name: '后端碎片率',
      description: '已分配与实际使用之间的碎片比例。',
      unit: 'percent',
      query:
        'clamp_min((etcd_mvcc_db_total_size_in_bytes_gauge{__$labels__} - etcd_mvcc_db_total_size_in_use_in_bytes_gauge{__$labels__}) / clamp_min(etcd_mvcc_db_total_size_in_bytes_gauge{__$labels__}, 1) * 100, 0)',
      color: '#ff8a1f'
    },
    {
      name: 'etcd_keys_total',
      display_name: '键数量',
      description: '存储中的键总数。',
      unit: 'counts',
      query: 'max by (instance_id) (etcd_debugging_mvcc_keys_total_gauge{__$labels__})',
      color: '#597ef7'
    },
    {
      name: 'etcd_put_rate',
      display_name: '写入频率',
      description: 'Put 操作频率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(etcd_mvcc_put_total_counter{__$labels__}[__$window__]))',
      color: '#27c274'
    },
    {
      name: 'etcd_delete_rate',
      display_name: '删除频率',
      description: 'Delete 操作频率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(etcd_mvcc_delete_total_counter{__$labels__}[__$window__]))',
      color: '#ff4d4f'
    }
  ],
  summaryCards: [
    {
      // 实例盘先认角色：主值=本机主/从；footer=集群是否已选出主（缺主才是紧急态）。
      title: '本机角色',
      metric: 'etcd_is_leader',
      color: '#2f6bff',
      icon: 'node',
      enumMap: IS_LEADER_ENUM,
      guide: [
        {
          label: '本机角色',
          detail: '当前打开的这台 etcd 成员是主节点还是从节点。写请求只由主节点处理；排查切主影响面时先确认自己在看哪台。'
        },
        {
          label: '集群主节点',
          detail: '集群是否具备可用的主节点。显示「主节点缺失」时读写会失败或阻塞，需立即排查网络分区与成员状态。'
        }
      ],
      footer: [{ label: '集群', metric: 'etcd_has_leader', enumMap: HAS_LEADER_ENUM }]
    },
    {
      title: '后端存储使用率',
      metric: 'etcd_backend_usage_pct',
      unit: 'percent',
      color: '#ff8a1f',
      icon: 'database',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: '后端配额',
          detail: '已分配空间占配额比例。接近上限会触发写保护；配合碎片率判断是否需 defrag。'
        }
      ],
      footer: [{ label: '剩余', metric: 'etcd_backend_remaining', unit: 'bytes' }]
    },
    {
      title: '提案积压',
      metric: 'etcd_proposals_pending',
      unit: 'counts',
      color: '#ff4d4f',
      icon: 'backlog',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: '提案积压',
          detail: '待处理提案数。持续非零常伴随 apply lag 或磁盘时延升高。'
        }
      ],
      footer: [{ label: 'Apply Lag', metric: 'etcd_apply_lag', unit: 'counts' }]
    },
    {
      title: 'WAL fsync P99',
      metric: 'etcd_wal_fsync_p99',
      unit: 's',
      color: '#722ed1',
      icon: 'clock',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: 'WAL fsync',
          detail: 'WAL 刷盘 P99 延迟。升高通常指向慢盘，是 etcd 性能与稳定性的关键信号。'
        }
      ]
    },
  ],
  charts: [
    {
      title: '磁盘时延',
      subtitle: 'WAL fsync / Backend commit P99',
      metric: 'etcd_wal_fsync_p99',
      guide: [
        { label: 'WAL', detail: 'WAL 刷盘 P99。' },
        { label: 'Backend', detail: '后端 commit P99。' }
      ],
      series: [
        { metric: 'etcd_wal_fsync_p99', label: 'WAL fsync P99', color: '#722ed1', unit: 's' },
        { metric: 'etcd_backend_commit_p99', label: 'Backend commit P99', color: '#8a5cff', unit: 's' }
      ]
    },
    {
      title: '切主与心跳',
      subtitle: '主节点切换 / 心跳失败',
      metric: 'etcd_leader_changes_rate',
      guide: [
        { label: '切主', detail: '主节点切换频率，频繁切换说明集群不稳。' },
        { label: '心跳失败', detail: '心跳发送失败速率。' }
      ],
      series: [
        { metric: 'etcd_leader_changes_rate', label: '切主', color: '#ff8a1f', unit: 'cps' },
        { metric: 'etcd_heartbeat_fail_rate', label: '心跳失败', color: '#ff4d4f', unit: 'cps' }
      ]
    },
    {
      title: 'Apply Lag',
      subtitle: '已提交未应用的提案数',
      metric: 'etcd_apply_lag',
      guide: [{ label: 'Apply Lag', detail: '已提交但未应用的提案积压，持续抬升需结合磁盘时延排查。' }],
      series: [{ metric: 'etcd_apply_lag', label: 'Apply Lag', color: '#faad14', unit: 'counts' }]
    },
    {
      title: '提案吞吐',
      subtitle: '提交 vs 应用 vs 失败',
      metric: 'etcd_proposals_committed_rate',
      guide: [
        { label: '提交/应用', detail: '提案提交与应用速率应大致匹配。' },
        { label: '失败', detail: '提案失败速率，非零需排查。' }
      ],
      series: [
        { metric: 'etcd_proposals_committed_rate', label: '提交', color: '#27c274', unit: 'cps' },
        { metric: 'etcd_proposals_applied_rate', label: '应用', color: '#2f6bff', unit: 'cps' },
        { metric: 'etcd_proposals_failed_rate', label: '失败', color: '#ff4d4f', unit: 'cps' }
      ]
    },
    {
      title: '后端碎片率',
      subtitle: '已分配与实际使用之间的碎片',
      metric: 'etcd_fragmentation_pct',
      guide: [{ label: '碎片', detail: '后端碎片率升高时考虑 defrag。' }],
      series: [{ metric: 'etcd_fragmentation_pct', label: '碎片率', color: '#ff8a1f', unit: 'percent' }]
    },
    {
      title: 'Put / Delete',
      subtitle: '写入与删除频率',
      metric: 'etcd_put_rate',
      guide: [{ label: '写入', detail: 'Put/Delete 操作频率。' }],
      series: [
        { metric: 'etcd_put_rate', label: 'Put', color: '#27c274', unit: 'cps' },
        { metric: 'etcd_delete_rate', label: 'Delete', color: '#ff4d4f', unit: 'cps' }
      ]
    }
  ],
  statusPanels: [],
  ringPanels: [],
  barPanels: [],
  details: []
};
