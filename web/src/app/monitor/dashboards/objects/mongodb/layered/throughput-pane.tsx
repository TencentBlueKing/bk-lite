'use client';

import { ProSection } from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import { MONGODB_PALETTE } from './metrics';
import { MongoTrend, type MongoSeriesSpec } from './trend';
import type { MongoMetricMap } from './series';

interface ChartSpec {
  anchor: string;
  title: string;
  body: string;
  series: readonly MongoSeriesSpec[];
  counts?: boolean;
  emptyText?: string;
}

const CHARTS: readonly ChartSpec[] = [
  {
    anchor: 'connections',
    title: '连接趋势',
    body: '当前连接、尚可接纳连接与打开连接的对照，用于观察连接余量与并发。',
    series: [
      { name: 'mongodb_connections_current', label: '当前连接', color: MONGODB_PALETTE.blue, unit: 'counts' },
      { name: 'mongodb_connections_available', label: '可用连接', color: MONGODB_PALETTE.violet, unit: 'counts' },
      { name: 'mongodb_open_connections', label: '打开连接', color: MONGODB_PALETTE.cyan, unit: 'counts' }
    ]
  },
  {
    anchor: 'throughput',
    title: '吞吐构成',
    body: '命令、查询与写入操作的每秒次数构成，反映读写负载结构。',
    series: [
      { name: 'mongodb_commands_rate', label: '命令', color: MONGODB_PALETTE.blue, unit: 'cps' },
      { name: 'mongodb_queries_rate', label: '查询', color: MONGODB_PALETTE.cyan, unit: 'cps' },
      { name: 'mongodb_write_ops_rate', label: '写入', color: MONGODB_PALETTE.orange, unit: 'cps' }
    ]
  },
  {
    anchor: 'documents',
    title: '文档操作吞吐',
    body: '每秒插入、更新、删除的文档数对照。',
    series: [
      { name: 'mongodb_document_inserted_rate', label: '插入', color: MONGODB_PALETTE.blue, unit: 'cps' },
      { name: 'mongodb_document_updated_rate', label: '更新', color: MONGODB_PALETTE.orange, unit: 'cps' },
      { name: 'mongodb_document_deleted_rate', label: '删除', color: MONGODB_PALETTE.red, unit: 'cps' }
    ]
  },
  {
    anchor: 'latency',
    title: '读写延迟',
    body: '命令平均延迟与读平均延迟对照，用于观察响应是否抬升。',
    series: [
      { name: 'mongodb_latency_commands_avg', label: '命令延迟', color: MONGODB_PALETTE.violet, unit: 'ms' },
      { name: 'mongodb_latency_reads_avg', label: '读延迟', color: MONGODB_PALETTE.green, unit: 'ms' }
    ]
  },
  {
    anchor: 'queue',
    title: '活跃与排队',
    body: '正在执行与正在等待的读/写操作数量对照。',
    series: [
      { name: 'mongodb_active_reads', label: '活跃读', color: MONGODB_PALETTE.blue, unit: 'counts' },
      { name: 'mongodb_active_writes', label: '活跃写', color: MONGODB_PALETTE.green, unit: 'counts' },
      { name: 'mongodb_queued_reads', label: '排队读', color: MONGODB_PALETTE.violet, unit: 'counts' },
      { name: 'mongodb_queued_writes', label: '排队写', color: MONGODB_PALETTE.orange, unit: 'counts' }
    ]
  },
  {
    anchor: 'network',
    title: '网络出入',
    body: '实例网络流入与流出速率对照。',
    series: [
      { name: 'mongodb_net_in_bytes_count_rate', label: '流入', color: MONGODB_PALETTE.blue, unit: 'byteps' },
      { name: 'mongodb_net_out_bytes_count_rate', label: '流出', color: MONGODB_PALETTE.green, unit: 'byteps' }
    ]
  },
  {
    anchor: 'assert',
    title: '用户断言次数',
    body: '当前时间范围内发生的用户断言次数。偶发需关注应用或数据异常；持续出现应排查写入校验与驱动用法。',
    counts: true,
    emptyText: '本窗口暂无用户断言数据。',
    series: [
      { name: 'mongodb_assert_user', label: '用户断言', color: MONGODB_PALETTE.red, unit: 'counts' }
    ]
  },
  {
    anchor: 'cursor',
    title: '游标超时次数',
    body: '当前时间范围内游标超时的次数。偏高常见于长查询未耗尽或游标未及时关闭。',
    counts: true,
    emptyText: '本窗口暂无游标超时数据。',
    series: [
      { name: 'mongodb_cursor_timed_out_count', label: '游标超时', color: MONGODB_PALETTE.amber, unit: 'counts' }
    ]
  }
];

export default function ThroughputPane({
  metricMap,
  pendingMetricNames
}: {
  metricMap: MongoMetricMap;
  pendingMetricNames: ReadonlySet<string>;
}) {
  return (
    <div data-mongodb-pane="throughput" className="contents">
      <ProSection title="连接与吞吐">
        <div className={host.chartGrid2} data-mongodb-zone="throughput">
          {CHARTS.map((chart) => (
            <MongoTrend
              key={chart.anchor}
              anchor={chart.anchor}
              title={chart.title}
              body={chart.body}
              series={chart.series}
              metricMap={metricMap}
              pending={pendingMetricNames}
              counts={chart.counts}
              emptyText={chart.emptyText}
            />
          ))}
        </div>
      </ProSection>
    </div>
  );
}
