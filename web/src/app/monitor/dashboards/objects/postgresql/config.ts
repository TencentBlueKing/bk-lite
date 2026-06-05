import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

export const POSTGRESQL_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'postgres',
  pageTitle: 'PostgreSQL 监控仪表盘',
  objectFallbackName: 'PostgreSQL',
  instanceType: 'postgres',
  collectionStatusQuery: "count({instance_type='postgres', collect_type='database', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'database'],
  metrics: [
    {
      name: 'postgresql_numbackends',
      display_name: '活跃连接数',
      description: '活跃数据库会话数量。',
      unit: 'counts',
      query: 'postgresql_numbackends{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'postgresql_xact_commit_rate',
      display_name: '事务提交速率',
      description: '已提交事务的速率。',
      unit: 'cps',
      query: 'rate(postgresql_xact_commit{__$labels__}[5m])',
      color: '#27c274'
    },
    {
      name: 'postgresql_xact_rollback_rate',
      display_name: '事务回滚速率',
      description: '回滚事务的速率。',
      unit: 'cps',
      query: 'rate(postgresql_xact_rollback{__$labels__}[5m])',
      color: '#ff4d4f'
    },
    {
      name: 'postgresql_tup_returned_rate',
      display_name: '查询返回行速率',
      description: '查询结果集中返回行的速率。',
      unit: 'cps',
      query: 'rate(postgresql_tup_returned{__$labels__}[5m])',
      color: '#2f6bff'
    },
    {
      name: 'postgresql_tup_fetched_rate',
      display_name: '查询提取行速率',
      description: '查询期间从存储中提取行的速率。',
      unit: 'cps',
      query: 'rate(postgresql_tup_fetched{__$labels__}[5m])',
      color: '#13c2c2'
    },
    {
      name: 'postgresql_tup_inserted_rate',
      display_name: '行插入速率',
      description: '行插入操作速率。',
      unit: 'cps',
      query: 'rate(postgresql_tup_inserted{__$labels__}[5m])',
      color: '#2f6bff'
    },
    {
      name: 'postgresql_tup_updated_rate',
      display_name: '行更新速率',
      description: '行更新操作速率。',
      unit: 'cps',
      query: 'rate(postgresql_tup_updated{__$labels__}[5m])',
      color: '#ff8a1f'
    },
    {
      name: 'postgresql_tup_deleted_rate',
      display_name: '行删除速率',
      description: '行删除操作速率。',
      unit: 'cps',
      query: 'rate(postgresql_tup_deleted{__$labels__}[5m])',
      color: '#ff4d4f'
    },
    {
      name: 'postgresql_blks_hit_rate',
      display_name: '缓存命中速率',
      description: '共享缓冲区命中块速率。',
      unit: 'cps',
      query: 'rate(postgresql_blks_hit{__$labels__}[5m])',
      color: '#27c274'
    },
    {
      name: 'postgresql_blks_read_rate',
      display_name: '磁盘块读取速率',
      description: '需从磁盘读取块的速率。',
      unit: 'cps',
      query: 'rate(postgresql_blks_read{__$labels__}[5m])',
      color: '#ff8a1f'
    },
    {
      name: 'postgresql_cache_hit_ratio',
      display_name: '缓存命中率',
      description: '共享缓冲区缓存命中比例。',
      unit: 'percent',
      query: '100 * rate(postgresql_blks_hit{__$labels__}[5m]) / clamp_min(rate(postgresql_blks_hit{__$labels__}[5m]) + rate(postgresql_blks_read{__$labels__}[5m]), 1e-6)',
      color: '#27c274'
    },
    {
      name: 'postgresql_deadlocks_rate',
      display_name: '死锁速率',
      description: '事务死锁发生速率。',
      unit: 'cps',
      query: 'rate(postgresql_deadlocks{__$labels__}[5m])',
      color: '#ff4d4f'
    },
    {
      name: 'postgresql_conflicts_rate',
      display_name: '并发冲突速率',
      description: '并发操作冲突速率。',
      unit: 'cps',
      query: 'rate(postgresql_conflicts{__$labels__}[5m])',
      color: '#faad14'
    },
    {
      name: 'postgresql_temp_files_rate',
      display_name: '临时文件创建速率',
      description: '复杂查询创建临时文件的速率。',
      unit: 'cps',
      query: 'rate(postgresql_temp_files{__$labels__}[5m])',
      color: '#faad14'
    },
    {
      name: 'postgresql_temp_bytes_rate',
      display_name: '临时文件写入吞吐',
      description: '临时文件写入数据速率。',
      unit: 'byteps',
      query: 'rate(postgresql_temp_bytes{__$labels__}[5m])',
      color: '#8a5cff'
    },
    {
      name: 'postgresql_checkpoints_timed_rate',
      display_name: '定时检查点速率',
      description: '系统触发检查点速率。',
      unit: 'cps',
      query: 'rate(postgresql_checkpoints_timed{__$labels__}[5m])',
      color: '#2f6bff'
    },
    {
      name: 'postgresql_checkpoints_req_rate',
      display_name: '请求检查点速率',
      description: '请求触发检查点速率。',
      unit: 'cps',
      query: 'rate(postgresql_checkpoints_req{__$labels__}[5m])',
      color: '#ff8a1f'
    },
    {
      name: 'postgresql_buffers_alloc_rate',
      display_name: '缓冲区分配速率',
      description: '共享缓冲区分配速率。',
      unit: 'cps',
      query: 'rate(postgresql_buffers_alloc{__$labels__}[5m])',
      color: '#13c2c2'
    },
    {
      name: 'postgresql_buffers_backend_rate',
      display_name: '后端缓冲区写入速率',
      description: '后端进程直接写出缓冲区的速率。',
      unit: 'cps',
      query: 'rate(postgresql_buffers_backend{__$labels__}[5m])',
      color: '#ff8a1f'
    },
    {
      name: 'postgresql_buffers_checkpoint_rate',
      display_name: '检查点写入速率',
      description: '检查点期间写出缓冲区的速率。',
      unit: 'cps',
      query: 'rate(postgresql_buffers_checkpoint{__$labels__}[5m])',
      color: '#2f6bff'
    },
    {
      name: 'postgresql_maxwritten_clean_rate',
      display_name: '后台清理写入速率',
      description: '后台清理进程写出页的速率。',
      unit: 'cps',
      query: 'rate(postgresql_maxwritten_clean{__$labels__}[5m])',
      color: '#8a5cff'
    }
  ],
  summaryCards: [
    {
      title: '活跃连接数',
      metric: 'postgresql_numbackends',
      color: '#2f6bff',
      icon: 'node',
      guide: [{ label: '活跃连接', detail: '当前活跃数据库会话数量，用于评估并发负载。' }],
      footer: [{ label: '冲突速率', metric: 'postgresql_conflicts_rate', unit: 'cps' }]
    },
    {
      title: '事务提交速率',
      metric: 'postgresql_xact_commit_rate',
      color: '#27c274',
      icon: 'thunder',
      guide: [{ label: '事务提交', detail: '成功提交事务的速率，反映业务活跃程度。' }],
      footer: [{ label: '回滚速率', metric: 'postgresql_xact_rollback_rate', unit: 'cps' }]
    },
    {
      title: '事务回滚速率',
      metric: 'postgresql_xact_rollback_rate',
      color: '#ff4d4f',
      icon: 'thunder',
      compare: true,
      guide: [{ label: '事务回滚', detail: '回滚事务速率，持续升高需检查失败或冲突原因。' }],
      footer: [{ label: '死锁速率', metric: 'postgresql_deadlocks_rate', unit: 'cps' }]
    },
    {
      title: '磁盘块读取',
      metric: 'postgresql_blks_read_rate',
      color: '#ff8a1f',
      icon: 'database',
      guide: [{ label: '磁盘块读取', detail: '需从磁盘读取块的速率，高值通常表示缓存未命中较多。' }],
      footer: [
        { label: '缓存命中', metric: 'postgresql_blks_hit_rate', unit: 'cps' },
        { label: '命中率', metric: 'postgresql_cache_hit_ratio', unit: 'percent' }
      ]
    },
    {
      title: '缓存命中率',
      metric: 'postgresql_cache_hit_ratio',
      color: '#27c274',
      icon: 'database',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [{ label: '缓存命中率', detail: '共享缓冲区缓存命中比例，偏低时要关注内存配置和热点数据是否频繁落盘。' }],
      footer: [{ label: '磁盘读取', metric: 'postgresql_blks_read_rate', unit: 'cps' }]
    },
    {
      title: '死锁速率',
      metric: 'postgresql_deadlocks_rate',
      color: '#ff4d4f',
      icon: 'api',
      compare: true,
      guide: [{ label: '死锁速率', detail: '事务死锁发生速率，非零时需要关注事务设计。' }],
      footer: [{ label: '并发冲突', metric: 'postgresql_conflicts_rate', unit: 'cps' }]
    },
    {
      title: '临时文件速率',
      metric: 'postgresql_temp_files_rate',
      color: '#faad14',
      icon: 'thunder',
      compare: true,
      guide: [{ label: '临时文件', detail: '临时文件创建速率，高值通常与复杂查询和 work_mem 配置相关。' }],
      footer: [{ label: '写入吞吐', metric: 'postgresql_temp_bytes_rate', unit: 'byteps' }]
    }
  ],
  charts: [
    {
      title: '事务提交与回滚',
      subtitle: '提交与回滚速率',
      metric: 'postgresql_xact_commit_rate',
      guide: [
        { label: '提交', detail: '成功提交的事务速率。' },
        { label: '回滚', detail: '失败或冲突回滚的事务速率。' }
      ],
      series: [
        { metric: 'postgresql_xact_commit_rate', label: '提交速率', color: '#27c274', unit: 'cps' },
        { metric: 'postgresql_xact_rollback_rate', label: '回滚速率', color: '#ff4d4f', unit: 'cps' }
      ]
    },
    {
      title: '数据操作速率',
      subtitle: '插入、更新、删除',
      metric: 'postgresql_tup_inserted_rate',
      guide: [{ label: '数据操作', detail: '行级插入、更新、删除操作速率。' }],
      series: [
        { metric: 'postgresql_tup_inserted_rate', label: '插入', color: '#2f6bff', unit: 'cps' },
        { metric: 'postgresql_tup_updated_rate', label: '更新', color: '#ff8a1f', unit: 'cps' },
        { metric: 'postgresql_tup_deleted_rate', label: '删除', color: '#ff4d4f', unit: 'cps' }
      ]
    },
    {
      title: '缓存与磁盘读',
      subtitle: '缓存命中与磁盘读',
      metric: 'postgresql_blks_hit_rate',
      guide: [
        { label: '缓存命中', detail: '由共享缓冲区满足的块读取速率。' },
        { label: '磁盘读取', detail: '需要从磁盘读取的块速率。' }
      ],
      series: [
        { metric: 'postgresql_blks_hit_rate', label: '缓存命中', color: '#27c274', unit: 'cps' },
        { metric: 'postgresql_blks_read_rate', label: '磁盘读取', color: '#ff8a1f', unit: 'cps' }
      ]
    },
    {
      title: '缓冲区写入活动',
      subtitle: '检查点与后端写入',
      metric: 'postgresql_buffers_checkpoint_rate',
      guide: [{ label: '缓冲区写入', detail: '检查点、后端和后台清理写出缓冲区的速率。' }],
      series: [
        { metric: 'postgresql_buffers_checkpoint_rate', label: '检查点写入', color: '#2f6bff', unit: 'cps' },
        { metric: 'postgresql_buffers_backend_rate', label: '后端写入', color: '#ff8a1f', unit: 'cps' },
        { metric: 'postgresql_maxwritten_clean_rate', label: '后台清理', color: '#8a5cff', unit: 'cps' }
      ]
    },
    {
      title: '查询行读取趋势',
      subtitle: '返回与提取行数',
      metric: 'postgresql_tup_returned_rate',
      guide: [
        { label: '返回行', detail: '查询结果集中返回行速率。' },
        { label: '提取行', detail: '查询期间从存储提取行速率。' }
      ],
      series: [
        { metric: 'postgresql_tup_returned_rate', label: '返回行', color: '#2f6bff', unit: 'cps' },
        { metric: 'postgresql_tup_fetched_rate', label: '提取行', color: '#13c2c2', unit: 'cps' }
      ]
    },
    {
      title: '检查点趋势',
      subtitle: '定时与请求触发',
      metric: 'postgresql_checkpoints_timed_rate',
      guide: [
        { label: '定时检查点', detail: '系统按计划触发的检查点速率。' },
        { label: '请求检查点', detail: '因 WAL 压力请求触发的检查点速率。' }
      ],
      series: [
        { metric: 'postgresql_checkpoints_timed_rate', label: '定时检查点', color: '#2f6bff', unit: 'cps' },
        { metric: 'postgresql_checkpoints_req_rate', label: '请求检查点', color: '#ff8a1f', unit: 'cps' }
      ]
    }
  ],
  barPanels: [
    {
      title: '异常事件热点',
      subtitle: '死锁、冲突与临时文件',
      showTrend: true,
      guide: [{ label: '异常事件', detail: '死锁、并发冲突与临时文件创建速率，用于快速定位异常负载。' }],
      items: [
        { label: '死锁速率', metric: 'postgresql_deadlocks_rate', color: '#ff4d4f', unit: 'cps' },
        { label: '并发冲突', metric: 'postgresql_conflicts_rate', color: '#faad14', unit: 'cps' },
        { label: '临时文件', metric: 'postgresql_temp_files_rate', color: '#8a5cff', unit: 'cps' }
      ]
    },
    {
      title: '缓冲区写入来源',
      subtitle: '检查点、后端与后台',
      showTrend: true,
      guide: [{ label: '写入来源', detail: '比较检查点、后端和后台清理写出缓冲区的压力来源。' }],
      items: [
        { label: '检查点写入', metric: 'postgresql_buffers_checkpoint_rate', color: '#2f6bff', unit: 'cps' },
        { label: '后端写入', metric: 'postgresql_buffers_backend_rate', color: '#ff8a1f', unit: 'cps' },
        { label: '后台清理', metric: 'postgresql_maxwritten_clean_rate', color: '#8a5cff', unit: 'cps' }
      ]
    }
  ],
  details: []
};
