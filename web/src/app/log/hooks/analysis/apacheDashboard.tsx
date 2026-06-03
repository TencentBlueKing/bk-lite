import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';

const APACHE_BASE =
  'collect_type:"apache" service.name:"bk-lite-analysis-sample"';
const APACHE_ACCESS_BASE = `${APACHE_BASE} event.dataset:"apache.access"`;
const APACHE_ERROR_BASE = `${APACHE_BASE} event.dataset:"apache.error"`;
const APACHE_STATUS = 'apache.access.response_code';
const APACHE_URL = 'apache.access.url';
const APACHE_IP = 'apache.access.remote_ip';
const APACHE_BYTES = 'apache.access.body_sent.bytes';
const APACHE_LEVEL = 'apache.error.level';
const TIME_BUCKET = '${_time}';
const APACHE_4XX_FILTER = `${APACHE_STATUS}:re("4..")`;
const APACHE_5XX_FILTER = `${APACHE_STATUS}:re("5..")`;
const APACHE_ERROR_STATUS_FILTER = `(${APACHE_4XX_FILTER} OR ${APACHE_5XX_FILTER})`;

const WEB_LEVEL_META: Record<
  string,
  { label: string; text: string; background: string }
> = {
  error: { label: 'Error', text: '#f5222d', background: 'rgba(245, 34, 45, 0.12)' },
  warn: { label: 'Warn', text: '#fa8c16', background: 'rgba(250, 140, 22, 0.12)' },
  warning: { label: 'Warn', text: '#fa8c16', background: 'rgba(250, 140, 22, 0.12)' },
  notice: { label: 'Notice', text: '#1677ff', background: 'rgba(22, 119, 255, 0.12)' }
};

const renderWebLevel = (value: unknown) => {
  const key = String(value || '').trim().toLowerCase();
  const meta = WEB_LEVEL_META[key] || {
    label: String(value || '--'),
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

const renderStatusTag = (value: unknown) => {
  const status = Number(value || 0);
  const colors =
    status >= 500
      ? { text: '#f5222d', background: 'rgba(245, 34, 45, 0.12)' }
      : status >= 400
        ? { text: '#fa8c16', background: 'rgba(250, 140, 22, 0.12)' }
        : { text: '#1677ff', background: 'rgba(22, 119, 255, 0.12)' };

  return (
    <span
      className="inline-flex min-w-[44px] items-center justify-center rounded px-2 py-0.5 text-xs font-medium"
      style={{ color: colors.text, backgroundColor: colors.background }}
    >
      {status || '--'}
    </span>
  );
};

export const useApacheDashboard = () => {
  const { t } = useTranslation();

  return {
    name: 'Apache 日志分析',
    desc: '',
    id: 'mock-apache',
    category: 'middleware',
    categoryName: t('log.analysis.category.middleware'),
    collectTypeName: 'apache',
    filters: { group: true, instance: true },
    other: {},
    view_sets: [
      {
        h: 2,
        w: 3,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: '总请求数',
        description: '当前时间范围内 Apache 请求总数',
        valueConfig: {
          chartType: 'apacheKpiCard',
          dataSource: 1,
          color: 'primary',
          displayMaps: { type: 'single', key: '_time', value: 'total_count' },
          dataSourceParams: {
            searchQuery: APACHE_ACCESS_BASE,
            query: `${APACHE_ACCESS_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 3,
        y: 0,
        i: uuidv4(),
        name: '4xx 请求数',
        description: '当前时间范围内 4xx 请求总数',
        valueConfig: {
          chartType: 'apacheKpiCard',
          dataSource: 1,
          color: 'warning',
          displayMaps: { type: 'single', key: '_time', value: 'error4xx' },
          dataSourceParams: {
            searchQuery: `${APACHE_ACCESS_BASE} ${APACHE_4XX_FILTER}`,
            query: `${APACHE_ACCESS_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${APACHE_4XX_FILTER}) as error4xx`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: '5xx 请求数',
        description: '当前时间范围内 5xx 请求总数',
        valueConfig: {
          chartType: 'apacheKpiCard',
          dataSource: 1,
          color: 'danger',
          displayMaps: { type: 'single', key: '_time', value: 'error5xx' },
          dataSourceParams: {
            searchQuery: `${APACHE_ACCESS_BASE} ${APACHE_5XX_FILTER}`,
            query: `${APACHE_ACCESS_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${APACHE_5XX_FILTER}) as error5xx`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: '响应字节总量',
        description: '当前时间范围内响应流量总量',
        valueConfig: {
          chartType: 'apacheKpiCard',
          dataSource: 1,
          color: 'info',
          displayMaps: { type: 'single', key: '_time', value: 'traffic_bytes' },
          dataSourceParams: {
            searchQuery: APACHE_ACCESS_BASE,
            query: `${APACHE_ACCESS_BASE} | math ${APACHE_BYTES} as response_bytes | stats by (_time:${TIME_BUCKET}) sum(response_bytes) as traffic_bytes`
          },
          valueFormatter: (value: number) => {
            if (!Number.isFinite(value)) return '--';
            if (value >= 1024 * 1024 * 1024) {
              return `${(value / 1024 / 1024 / 1024).toFixed(2)}GB`;
            }
            return `${(value / 1024 / 1024).toFixed(0)}MB`;
          }
        }
      },
      {
        h: 3,
        w: 7,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: '请求量与异常趋势',
        valueConfig: {
          chartType: 'apacheTrend',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: APACHE_ACCESS_BASE,
            query:
              `${APACHE_ACCESS_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count, count() if (${APACHE_4XX_FILTER}) as error4xx, count() if (${APACHE_5XX_FILTER}) as error5xx`
          }
        }
      },
      {
        h: 3,
        w: 5,
        x: 7,
        y: 2,
        i: uuidv4(),
        name: '状态码类别分布',
        valueConfig: {
          chartType: 'apachePie',
          dataSource: 1,
          displayMaps: { key: 'status_group', value: 'count' },
          dataSourceParams: {
            searchQuery: `${APACHE_ACCESS_BASE} ${APACHE_STATUS}:*`,
            queries: [
              { key: '2xx', query: `${APACHE_ACCESS_BASE} ${APACHE_STATUS}:"2*" | stats count() as count` },
              { key: '4xx', query: `${APACHE_ACCESS_BASE} ${APACHE_4XX_FILTER} | stats count() as count` },
              { key: '5xx', query: `${APACHE_ACCESS_BASE} ${APACHE_5XX_FILTER} | stats count() as count` }
            ],
            transformMode: 'statusGroupCounts'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: 'Top 错误 URL',
        valueConfig: {
          chartType: 'dockerBar',
          dataSource: 1,
          barColor: '#1677ff',
          displayMaps: { key: 'apache.access.url', value: 'count' },
          dataSourceParams: {
            searchQuery: `${APACHE_ACCESS_BASE} ${APACHE_ERROR_STATUS_FILTER} ${APACHE_URL}:*`,
            query:
              `${APACHE_ACCESS_BASE} ${APACHE_ERROR_STATUS_FILTER} ${APACHE_URL}:* | stats by (${APACHE_URL}) count() as count | sort by (count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: 'Top 异常客户端 IP',
        valueConfig: {
          chartType: 'dockerBar',
          dataSource: 1,
          barColor: '#13c2c2',
          displayMaps: { key: 'apache.access.remote_ip', value: 'count' },
          dataSourceParams: {
            searchQuery: `${APACHE_ACCESS_BASE} ${APACHE_ERROR_STATUS_FILTER} ${APACHE_IP}:*`,
            query:
              `${APACHE_ACCESS_BASE} ${APACHE_ERROR_STATUS_FILTER} ${APACHE_IP}:* | stats by (${APACHE_IP}) count() as count | sort by (count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 5,
        i: uuidv4(),
        name: '状态码类别排行',
        valueConfig: {
          chartType: 'dockerBar',
          dataSource: 1,
          barColor: '#722ed1',
          displayMaps: { key: 'status_group', value: 'count' },
          dataSourceParams: {
            searchQuery: `${APACHE_ACCESS_BASE} ${APACHE_STATUS}:*`,
            queries: [
              { key: '2xx', query: `${APACHE_ACCESS_BASE} ${APACHE_STATUS}:"2*" | stats count() as count` },
              { key: '4xx', query: `${APACHE_ACCESS_BASE} ${APACHE_4XX_FILTER} | stats count() as count` },
              { key: '5xx', query: `${APACHE_ACCESS_BASE} ${APACHE_5XX_FILTER} | stats count() as count` }
            ],
            transformMode: 'statusGroupCounts'
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: '最近 5xx 请求',
        valueConfig: {
          chartType: 'apacheTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 160 },
            { title: '状态码', dataIndex: 'apache.access.response_code', key: 'apache.access.response_code', width: 90, render: renderStatusTag },
            { title: '方法', dataIndex: 'apache.access.method', key: 'apache.access.method', width: 86 },
            { title: 'URL', dataIndex: 'apache.access.url', key: 'apache.access.url', width: 220 },
            { title: '客户端 IP', dataIndex: 'apache.access.remote_ip', key: 'apache.access.remote_ip', width: 128 }
          ],
          dataSourceParams: {
            searchQuery: `${APACHE_ACCESS_BASE} ${APACHE_5XX_FILTER}`,
            query: `${APACHE_ACCESS_BASE} ${APACHE_5XX_FILTER} | sort by (_time desc) | limit 20`
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
          chartType: 'apacheTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 160 },
            { title: '级别', dataIndex: 'apache.error.level', key: 'apache.error.level', width: 90, render: renderWebLevel },
            { title: '客户端', dataIndex: 'apache.error.client', key: 'apache.error.client', width: 120 },
            { title: '消息摘要', dataIndex: 'apache.error.message', key: 'apache.error.message', width: 360 }
          ],
          dataSourceParams: {
            searchQuery: `${APACHE_ERROR_BASE} ${APACHE_LEVEL}:*`,
            query: `${APACHE_ERROR_BASE} ${APACHE_LEVEL}:* | sort by (_time desc) | limit 20`
          }
        }
      }
    ]
  };
};
