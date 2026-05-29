import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';

const PG_BASE =
  'collect_type:"postgresql" service.name:"bk-lite-analysis-sample" event.dataset:"postgresql.log"';
const PG_LEVEL = 'postgresql.log.level';
const PG_DB = 'postgresql.log.database';
const PG_USER = 'postgresql.log.user';
const PG_DURATION = 'postgresql.log.duration';
const TIME_BUCKET = '${_time}';

const PG_LEVEL_META: Record<
  string,
  { label: string; text: string; background: string }
> = {
  log: { label: 'LOG', text: '#1677ff', background: 'rgba(22, 119, 255, 0.12)' },
  warning: { label: 'WARNING', text: '#fa8c16', background: 'rgba(250, 140, 22, 0.12)' },
  error: { label: 'ERROR', text: '#f5222d', background: 'rgba(245, 34, 45, 0.12)' },
  fatal: { label: 'FATAL', text: '#722ed1', background: 'rgba(114, 46, 209, 0.12)' }
};

const renderPgLevel = (value: unknown) => {
  const key = String(value || '').trim().toLowerCase();
  const meta = PG_LEVEL_META[key] || {
    label: String(value || '--').toUpperCase(),
    text: '#5a6d7f',
    background: 'rgba(90, 109, 127, 0.12)'
  };

  return (
    <span
      className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium"
      style={{ color: meta.text, backgroundColor: meta.background }}
    >
      {meta.label}
    </span>
  );
};

export const usePostgresqlDashboard = () => {
  const { t } = useTranslation();

  return {
    name: 'PostgreSQL 日志分析',
    desc: '',
    id: 'mock-postgresql',
    category: 'middleware',
    categoryName: t('log.analysis.category.middleware'),
    collectTypeName: 'postgresql',
    filters: { group: true, instance: true },
    other: {},
    view_sets: [
      {
        h: 2,
        w: 3,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: '总日志数',
        description: '当前时间范围内 PostgreSQL 日志总数',
        valueConfig: {
          chartType: 'postgresqlKpiCard',
          dataSource: 1,
          color: 'primary',
          displayMaps: { type: 'single', key: '_time', value: 'total_count' },
          dataSourceParams: {
            searchQuery: PG_BASE,
            query: `${PG_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 3,
        y: 0,
        i: uuidv4(),
        name: 'Error / Fatal 日志数',
        description: '当前时间范围内异常日志总数',
        valueConfig: {
          chartType: 'postgresqlKpiCard',
          dataSource: 1,
          color: 'danger',
          displayMaps: { type: 'single', key: '_time', value: 'error_count' },
          dataSourceParams: {
            searchQuery: `${PG_BASE} (${PG_LEVEL}:"ERROR" OR ${PG_LEVEL}:"FATAL")`,
            query: `${PG_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${PG_LEVEL}:"ERROR" OR ${PG_LEVEL}:"FATAL") as error_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: '慢 SQL 数',
        description: '当前时间范围内慢 SQL 总数',
        valueConfig: {
          chartType: 'postgresqlKpiCard',
          dataSource: 1,
          color: 'warning',
          displayMaps: { type: 'single', key: '_time', value: 'slow_count' },
          dataSourceParams: {
            searchQuery: `${PG_BASE} ${PG_DURATION}:*`,
            query: `${PG_BASE} | math ${PG_DURATION} as duration_value | stats by (_time:${TIME_BUCKET}) count() if (duration_value:>=1) as slow_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: '客户端活跃数',
        description: '当前时间范围内涉及客户端地址的日志计数',
        valueConfig: {
          chartType: 'postgresqlKpiCard',
          dataSource: 1,
          color: 'info',
          metricMode: 'latest',
          displayMaps: { type: 'single', key: '_time', value: 'client_count' },
          dataSourceParams: {
            searchQuery: `${PG_BASE} postgresql.log.client_addr:*`,
            query: `${PG_BASE} postgresql.log.client_addr:* | stats by (_time:${TIME_BUCKET},postgresql.log.client_addr) count() as client_logs | stats by (_time) count() as client_count`
          }
        }
      },
      {
        h: 3,
        w: 7,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: '日志量与慢 SQL 趋势',
        valueConfig: {
          chartType: 'postgresqlTrend',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: PG_BASE,
            query:
              `${PG_BASE} | math ${PG_DURATION} as duration_value | stats by (_time:${TIME_BUCKET}) count() as total_count, count() if (${PG_LEVEL}:"ERROR" OR ${PG_LEVEL}:"FATAL") as error_count, count() if (duration_value:>=1) as slow_count, count() if (postgresql.log.client_addr:*) as client_count`
          }
        }
      },
      {
        h: 3,
        w: 5,
        x: 7,
        y: 2,
        i: uuidv4(),
        name: '异常级别分布',
        valueConfig: {
          chartType: 'postgresqlPie',
          dataSource: 1,
          displayMaps: { key: 'postgresql.log.level', value: 'count' },
          dataSourceParams: {
            searchQuery: `${PG_BASE} ${PG_LEVEL}:*`,
            query: `${PG_BASE} ${PG_LEVEL}:* | stats by (${PG_LEVEL}) count() as count | sort by (count desc)`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: 'Top 出错数据库',
        valueConfig: {
          chartType: 'dockerBar',
          dataSource: 1,
          barColor: '#1677ff',
          displayMaps: { key: 'postgresql.log.database', value: 'count' },
          dataSourceParams: {
            searchQuery: `${PG_BASE} (${PG_LEVEL}:"ERROR" OR ${PG_LEVEL}:"FATAL") ${PG_DB}:*`,
            query: `${PG_BASE} (${PG_LEVEL}:"ERROR" OR ${PG_LEVEL}:"FATAL") ${PG_DB}:* | stats by (${PG_DB}) count() as count | sort by (count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: 'Top 慢 SQL 用户',
        valueConfig: {
          chartType: 'dockerBar',
          dataSource: 1,
          barColor: '#13c2c2',
          displayMaps: { key: 'postgresql.log.user', value: 'count' },
          dataSourceParams: {
            searchQuery: `${PG_BASE} ${PG_USER}:* ${PG_DURATION}:*`,
            query: `${PG_BASE} ${PG_USER}:* | math ${PG_DURATION} as duration_value | stats by (${PG_USER}) count() if (duration_value:>=1) as count | sort by (count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 5,
        i: uuidv4(),
        name: '异常级别排行',
        valueConfig: {
          chartType: 'dockerBar',
          dataSource: 1,
          barColor: '#722ed1',
          displayMaps: { key: 'postgresql.log.level', value: 'count' },
          dataSourceParams: {
            searchQuery: `${PG_BASE} ${PG_LEVEL}:*`,
            query: `${PG_BASE} ${PG_LEVEL}:* | stats by (${PG_LEVEL}) count() as count | sort by (count desc)`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: '最近慢 SQL',
        valueConfig: {
          chartType: 'postgresqlTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 156 },
            { title: '数据库', dataIndex: 'postgresql.log.database', key: 'postgresql.log.database', width: 110 },
            { title: '用户', dataIndex: 'postgresql.log.user', key: 'postgresql.log.user', width: 110 },
            { title: '耗时', dataIndex: 'postgresql.log.duration', key: 'postgresql.log.duration', width: 90 },
            { title: 'SQL 摘要', dataIndex: 'postgresql.log.query', key: 'postgresql.log.query', width: 320 }
          ],
          dataSourceParams: {
            searchQuery: `${PG_BASE} ${PG_DURATION}:*`,
            query: `${PG_BASE} | math ${PG_DURATION} as duration_value | filter duration_value:>=1 | sort by (_time desc) | limit 20`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 6,
        y: 8,
        i: uuidv4(),
        name: '最近错误日志',
        valueConfig: {
          chartType: 'postgresqlTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 156 },
            { title: '数据库', dataIndex: 'postgresql.log.database', key: 'postgresql.log.database', width: 110 },
            { title: '用户', dataIndex: 'postgresql.log.user', key: 'postgresql.log.user', width: 110 },
            { title: '级别', dataIndex: 'postgresql.log.level', key: 'postgresql.log.level', width: 92, render: renderPgLevel },
            { title: '摘要', dataIndex: 'postgresql.log.message', key: 'postgresql.log.message', width: 320 }
          ],
          dataSourceParams: {
            searchQuery: `${PG_BASE} (${PG_LEVEL}:"ERROR" OR ${PG_LEVEL}:"FATAL")`,
            query: `${PG_BASE} (${PG_LEVEL}:"ERROR" OR ${PG_LEVEL}:"FATAL") | sort by (_time desc) | limit 20`
          }
        }
      }
    ]
  };
};
