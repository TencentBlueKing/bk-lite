import { useTranslation } from '@/utils/i18n';
import { Progress } from 'antd';
import { v4 as uuidv4 } from 'uuid';

const ES_BASE =
  'collect_type:"elasticsearch" service.name:"bk-lite-analysis-sample"';
const ES_SERVER_BASE = `${ES_BASE} event.dataset:"elasticsearch.server"`;
const ES_SLOWLOG_BASE = `${ES_BASE} event.dataset:"elasticsearch.slowlog"`;
const ES_LEVEL = 'elasticsearch.server.level';
const ES_COMPONENT = 'elasticsearch.server.component';
const ES_NODE = 'elasticsearch.server.node.name';
const ES_SLOW_INDEX = 'elasticsearch.slowlog.index';
const ES_SLOW_TYPE = 'elasticsearch.slowlog.type';
const ES_SLOW_TOOK = 'elasticsearch.slowlog.took';
const TIME_BUCKET = '${_time}';

const parsePercent = (value: unknown) => {
  const parsed = Number.parseFloat(String(value ?? '').replace('%', ''));
  return Number.isNaN(parsed) ? 0 : parsed;
};

const renderRatioProgress = (value: unknown) => {
  const percent = parsePercent(value);

  return (
    <div className="flex min-w-[112px] items-center gap-2">
      <Progress
        percent={percent}
        size="small"
        showInfo={false}
        strokeColor="#1677ff"
        trailColor="rgba(0, 0, 0, 0.06)"
        className="mb-0 min-w-0 flex-1"
      />
      <span className="min-w-[44px] text-xs text-[var(--color-text-2)]">
        {String(value || '--')}
      </span>
    </div>
  );
};

const renderEsLevel = (value: unknown) => {
  const text = String(value || '').toUpperCase();
  const colorMap: Record<string, { text: string; background: string }> = {
    ERROR: { text: '#f5222d', background: 'rgba(245, 34, 45, 0.12)' },
    WARN: { text: '#fa8c16', background: 'rgba(250, 140, 22, 0.12)' },
    WARNING: { text: '#fa8c16', background: 'rgba(250, 140, 22, 0.12)' },
    INFO: { text: '#1677ff', background: 'rgba(22, 119, 255, 0.12)' }
  };
  const colors = colorMap[text] || {
    text: '#5a6d7f',
    background: 'rgba(90, 109, 127, 0.12)'
  };

  return (
    <span
      className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium"
      style={{ color: colors.text, backgroundColor: colors.background }}
    >
      {text || '--'}
    </span>
  );
};

export const useElasticsearchDashboard = () => {
  const { t } = useTranslation();

  return {
    name: 'Elasticsearch 日志分析仪表盘',
    desc: '',
    id: 'mock-elasticsearch',
    category: 'middleware',
    categoryName: t('log.analysis.category.middleware'),
    collectTypeName: 'elasticsearch',
    filters: { group: true, instance: true },
    other: {},
    view_sets: [
      {
        h: 2,
        w: 2,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: '总日志数',
        description: '当前时间范围内 Elasticsearch 日志总数',
        valueConfig: {
          chartType: 'elasticsearchKpiCard',
          dataSource: 1,
          color: 'primary',
          displayMaps: { type: 'single', key: '_time', value: 'total_count' },
          dataSourceParams: {
            searchQuery: ES_BASE,
            query: `${ES_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count`
          }
        }
      },
      {
        h: 2,
        w: 2,
        x: 2,
        y: 0,
        i: uuidv4(),
        name: 'Error 日志数',
        description: '当前时间范围内 Error 日志总数',
        valueConfig: {
          chartType: 'elasticsearchKpiCard',
          dataSource: 1,
          color: 'danger',
          displayMaps: { type: 'single', key: '_time', value: 'error_count' },
          dataSourceParams: {
            searchQuery: `${ES_SERVER_BASE} ${ES_LEVEL}:"ERROR"`,
            query: `${ES_SERVER_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${ES_LEVEL}:"ERROR") as error_count`
          }
        }
      },
      {
        h: 2,
        w: 2,
        x: 4,
        y: 0,
        i: uuidv4(),
        name: 'Warn 日志数',
        description: '当前时间范围内 Warn 日志总数',
        valueConfig: {
          chartType: 'elasticsearchKpiCard',
          dataSource: 1,
          color: 'warning',
          displayMaps: { type: 'single', key: '_time', value: 'warn_count' },
          dataSourceParams: {
            searchQuery: `${ES_SERVER_BASE} ${ES_LEVEL}:"WARN"`,
            query: `${ES_SERVER_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${ES_LEVEL}:"WARN") as warn_count`
          }
        }
      },
      {
        h: 2,
        w: 2,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: '慢查询/慢写入数',
        description: '当前时间范围内慢查询/慢写入日志总数',
        valueConfig: {
          chartType: 'elasticsearchKpiCard',
          dataSource: 1,
          color: 'accent',
          displayMaps: { type: 'single', key: '_time', value: 'slow_count' },
          dataSourceParams: {
            searchQuery: ES_SLOWLOG_BASE,
            query: `${ES_SLOWLOG_BASE} | stats by (_time:${TIME_BUCKET}) count() as slow_count`
          }
        }
      },
      {
        h: 2,
        w: 2,
        x: 8,
        y: 0,
        i: uuidv4(),
        name: '慢日志数',
        description: '当前时间范围内慢查询/慢写入日志总数',
        valueConfig: {
          chartType: 'elasticsearchKpiCard',
          dataSource: 1,
          color: 'info',
          displayMaps: { type: 'single', key: '_time', value: 'slow_count' },
          dataSourceParams: {
            searchQuery: ES_SLOWLOG_BASE,
            query: `${ES_SLOWLOG_BASE} | stats by (_time:${TIME_BUCKET}) count() as slow_count`
          }
        }
      },
      {
        h: 2,
        w: 2,
        x: 10,
        y: 0,
        i: uuidv4(),
        name: '活跃节点数',
        description: '当前时间范围内产生日志的活跃节点数',
        valueConfig: {
          chartType: 'elasticsearchKpiCard',
          dataSource: 1,
          color: '#2f54eb',
          metricMode: 'latest',
          displayMaps: { type: 'single', key: '_time', value: 'node_count' },
          dataSourceParams: {
            searchQuery: `${ES_SERVER_BASE} ${ES_NODE}:*`,
            query: `${ES_SERVER_BASE} ${ES_NODE}:* | stats by (_time:${TIME_BUCKET},${ES_NODE}) count() as log_count | stats by (_time) count() as node_count`
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: '日志量与高危日志趋势',
        valueConfig: {
          chartType: 'elasticsearchTrend',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: ES_BASE,
            query: `${ES_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count, count() if (${ES_LEVEL}:"ERROR") as error_count, count() if (${ES_LEVEL}:"WARN") as warn_count, count() if (event.dataset:"elasticsearch.slowlog") as slow_count`
          }
        }
      },
      {
        h: 3,
        w: 6,
        x: 6,
        y: 2,
        i: uuidv4(),
        name: '日志级别分布',
        valueConfig: {
          chartType: 'elasticsearchPie',
          dataSource: 1,
          displayMaps: { key: 'elasticsearch.server.level', value: 'count' },
          dataSourceParams: {
            searchQuery: `${ES_SERVER_BASE} ${ES_LEVEL}:*`,
            query: `${ES_SERVER_BASE} ${ES_LEVEL}:* | stats by (${ES_LEVEL}) count() as count | sort by (count desc)`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: 'Top 异常节点',
        valueConfig: {
          chartType: 'elasticsearchTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: '节点名称', dataIndex: 'elasticsearch.server.node.name', key: 'elasticsearch.server.node.name', width: 160 },
            { title: 'Error (条)', dataIndex: 'error_count', key: 'error_count', width: 110 },
            { title: 'Warn (条)', dataIndex: 'warn_count', key: 'warn_count', width: 110 },
            { title: '慢日志 (条)', dataIndex: 'slow_count', key: 'slow_count', width: 110 },
            { title: '长 GC (次)', dataIndex: 'gc_count', key: 'gc_count', width: 96 }
          ],
          dataSourceParams: {
            queries: [
              {
                key: 'serverRows',
                query: `${ES_SERVER_BASE} ${ES_NODE}:* | stats by (${ES_NODE}) count() if (${ES_LEVEL}:"ERROR") as error_count, count() if (${ES_LEVEL}:"WARN") as warn_count | sort by (error_count desc, warn_count desc) | limit 10`
              },
              {
                key: 'slowRows',
                query: `${ES_SLOWLOG_BASE} instance_id:* | stats by (instance_id) count() as slow_count | sort by (slow_count desc) | limit 10`
              }
            ],
            transformMode: 'esNodes'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: 'Top 慢日志索引',
        valueConfig: {
          chartType: 'elasticsearchTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: '索引名称', dataIndex: 'elasticsearch.slowlog.index', key: 'elasticsearch.slowlog.index', width: 180 },
            { title: '类型', dataIndex: 'elasticsearch.slowlog.type', key: 'elasticsearch.slowlog.type', width: 90 },
            { title: '慢日志数 (条)', dataIndex: 'slow_count', key: 'slow_count', width: 110 },
            { title: 'P95 耗时 (ms)', dataIndex: 'p95_duration', key: 'p95_duration', width: 120 }
          ],
          dataSourceParams: {
            searchQuery: `${ES_SLOWLOG_BASE} ${ES_SLOW_INDEX}:*`,
            query: `${ES_SLOWLOG_BASE} ${ES_SLOW_INDEX}:* | extract "<p95_duration>ms" from ${ES_SLOW_TOOK} | stats by (${ES_SLOW_INDEX},${ES_SLOW_TYPE}) count() as slow_count, max(p95_duration) as p95_duration | sort by (slow_count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 5,
        i: uuidv4(),
        name: 'Top 异常组件',
        valueConfig: {
          chartType: 'elasticsearchTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: '组件', dataIndex: 'elasticsearch.server.component', key: 'elasticsearch.server.component', width: 180 },
            { title: 'Error (条)', dataIndex: 'error_count', key: 'error_count', width: 120 },
            { title: 'Warn (条)', dataIndex: 'warn_count', key: 'warn_count', width: 120 },
            { title: '占比', dataIndex: 'ratio', key: 'ratio', width: 140, render: renderRatioProgress }
          ],
          dataSourceParams: {
            searchQuery: `${ES_SERVER_BASE} ${ES_COMPONENT}:*`,
            query: `${ES_SERVER_BASE} ${ES_COMPONENT}:* | stats by (${ES_COMPONENT}) count() if (${ES_LEVEL}:"ERROR") as error_count, count() if (${ES_LEVEL}:"WARN") as warn_count | sort by (error_count desc, warn_count desc) | limit 10`,
            transformMode: 'esTopComponents'
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: '最近慢查询/慢写入明细',
        valueConfig: {
          chartType: 'elasticsearchTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 160 },
            { title: '节点', dataIndex: 'instance_id', key: 'instance_id', width: 140 },
            { title: '索引', dataIndex: 'elasticsearch.slowlog.index', key: 'elasticsearch.slowlog.index', width: 160 },
            { title: '类型', dataIndex: 'elasticsearch.slowlog.type', key: 'elasticsearch.slowlog.type', width: 90 },
            { title: '耗时', dataIndex: 'elasticsearch.slowlog.took', key: 'elasticsearch.slowlog.took', width: 96 },
            { title: 'source 摘要', dataIndex: 'elasticsearch.slowlog.source', key: 'elasticsearch.slowlog.source', width: 360 }
          ],
          dataSourceParams: {
            searchQuery: ES_SLOWLOG_BASE,
            query: `${ES_SLOWLOG_BASE} | sort by (_time desc) | limit 20`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 6,
        y: 8,
        i: uuidv4(),
        name: '最近服务异常日志',
        valueConfig: {
          chartType: 'elasticsearchTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 160 },
            { title: '节点', dataIndex: 'elasticsearch.server.node.name', key: 'elasticsearch.server.node.name', width: 140 },
            { title: '级别', dataIndex: 'elasticsearch.server.level', key: 'elasticsearch.server.level', width: 90, render: renderEsLevel },
            { title: '组件', dataIndex: 'elasticsearch.server.component', key: 'elasticsearch.server.component', width: 120 },
            { title: '消息摘要', dataIndex: 'elasticsearch.server.message', key: 'elasticsearch.server.message', width: 320 }
          ],
          dataSourceParams: {
            searchQuery: `${ES_SERVER_BASE} (${ES_LEVEL}:"ERROR" OR ${ES_LEVEL}:"WARN")`,
            query: `${ES_SERVER_BASE} (${ES_LEVEL}:"ERROR" OR ${ES_LEVEL}:"WARN") | sort by (_time desc) | limit 20`
          }
        }
      }
    ]
  };
};
