import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';

const NGINX_BASE =
  'collect_type:"nginx" service.name:"bk-lite-analysis-sample"';
const NGINX_ACCESS_BASE = `${NGINX_BASE} event.dataset:"nginx.access"`;
const NGINX_ERROR_BASE = `${NGINX_BASE} event.dataset:"nginx.error"`;
const NGINX_STATUS = 'nginx.access.response_code';
const NGINX_URL = 'nginx.access.url';
const NGINX_REFERRER = 'nginx.access.referrer';
const NGINX_BYTES = 'nginx.access.body_sent.bytes';
const NGINX_LEVEL = 'nginx.error.level';
const TIME_BUCKET = '${_time}';
const NGINX_4XX_FILTER = `${NGINX_STATUS}:re("4..")`;
const NGINX_5XX_FILTER = `${NGINX_STATUS}:re("5..")`;
const NGINX_ERROR_STATUS_FILTER = `(${NGINX_4XX_FILTER} OR ${NGINX_5XX_FILTER})`;

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

export const useNginxDashboard = () => {
  const { t } = useTranslation();

  return {
    name: 'Nginx 日志分析',
    desc: '',
    id: 'mock-nginx',
    category: 'middleware',
    categoryName: t('log.analysis.category.middleware'),
    collectTypeName: 'nginx',
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
        description: '当前时间范围内 Nginx 请求总数',
        valueConfig: {
          chartType: 'nginxKpiCard',
          dataSource: 1,
          color: 'primary',
          displayMaps: { type: 'single', key: '_time', value: 'total_count' },
          dataSourceParams: {
            searchQuery: NGINX_ACCESS_BASE,
            query: `${NGINX_ACCESS_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count`
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
          chartType: 'nginxKpiCard',
          dataSource: 1,
          color: 'warning',
          displayMaps: { type: 'single', key: '_time', value: 'error4xx' },
          dataSourceParams: {
            searchQuery: `${NGINX_ACCESS_BASE} ${NGINX_4XX_FILTER}`,
            query: `${NGINX_ACCESS_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${NGINX_4XX_FILTER}) as error4xx`
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
          chartType: 'nginxKpiCard',
          dataSource: 1,
          color: 'danger',
          displayMaps: { type: 'single', key: '_time', value: 'error5xx' },
          dataSourceParams: {
            searchQuery: `${NGINX_ACCESS_BASE} ${NGINX_5XX_FILTER}`,
            query: `${NGINX_ACCESS_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${NGINX_5XX_FILTER}) as error5xx`
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
          chartType: 'nginxKpiCard',
          dataSource: 1,
          color: 'info',
          displayMaps: { type: 'single', key: '_time', value: 'traffic_bytes' },
          dataSourceParams: {
            searchQuery: NGINX_ACCESS_BASE,
            query: `${NGINX_ACCESS_BASE} | math ${NGINX_BYTES} as response_bytes | stats by (_time:${TIME_BUCKET}) sum(response_bytes) as traffic_bytes`
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
          chartType: 'nginxTrend',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: NGINX_ACCESS_BASE,
            query:
              `${NGINX_ACCESS_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count, count() if (${NGINX_4XX_FILTER}) as error4xx, count() if (${NGINX_5XX_FILTER}) as error5xx`
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
          chartType: 'nginxPie',
          dataSource: 1,
          displayMaps: { key: 'status_group', value: 'count' },
          dataSourceParams: {
            searchQuery: `${NGINX_ACCESS_BASE} ${NGINX_STATUS}:*`,
            queries: [
              { key: '2xx', query: `${NGINX_ACCESS_BASE} ${NGINX_STATUS}:"2*" | stats count() as count` },
              { key: '4xx', query: `${NGINX_ACCESS_BASE} ${NGINX_4XX_FILTER} | stats count() as count` },
              { key: '5xx', query: `${NGINX_ACCESS_BASE} ${NGINX_5XX_FILTER} | stats count() as count` }
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
          displayMaps: { key: 'nginx.access.url', value: 'count' },
          dataSourceParams: {
            searchQuery: `${NGINX_ACCESS_BASE} ${NGINX_ERROR_STATUS_FILTER} ${NGINX_URL}:*`,
            query:
              `${NGINX_ACCESS_BASE} ${NGINX_ERROR_STATUS_FILTER} ${NGINX_URL}:* | stats by (${NGINX_URL}) count() as count | sort by (count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: 'Top 异常来源页面',
        valueConfig: {
          chartType: 'dockerBar',
          dataSource: 1,
          barColor: '#13c2c2',
          displayMaps: { key: 'nginx.access.referrer', value: 'count' },
          dataSourceParams: {
            searchQuery: `${NGINX_ACCESS_BASE} ${NGINX_ERROR_STATUS_FILTER} ${NGINX_REFERRER}:*`,
            query:
              `${NGINX_ACCESS_BASE} ${NGINX_ERROR_STATUS_FILTER} ${NGINX_REFERRER}:* | stats by (${NGINX_REFERRER}) count() as count | sort by (count desc) | limit 10`
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
            searchQuery: `${NGINX_ACCESS_BASE} ${NGINX_STATUS}:*`,
            queries: [
              { key: '2xx', query: `${NGINX_ACCESS_BASE} ${NGINX_STATUS}:"2*" | stats count() as count` },
              { key: '4xx', query: `${NGINX_ACCESS_BASE} ${NGINX_4XX_FILTER} | stats count() as count` },
              { key: '5xx', query: `${NGINX_ACCESS_BASE} ${NGINX_5XX_FILTER} | stats count() as count` }
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
          chartType: 'nginxTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 160 },
            { title: '状态码', dataIndex: 'nginx.access.response_code', key: 'nginx.access.response_code', width: 90, render: renderStatusTag },
            { title: '方法', dataIndex: 'nginx.access.method', key: 'nginx.access.method', width: 86 },
            { title: 'URL', dataIndex: 'nginx.access.url', key: 'nginx.access.url', width: 220 },
            { title: '客户端 IP', dataIndex: 'nginx.access.remote_ip', key: 'nginx.access.remote_ip', width: 128 }
          ],
          dataSourceParams: {
            searchQuery: `${NGINX_ACCESS_BASE} ${NGINX_5XX_FILTER}`,
            query: `${NGINX_ACCESS_BASE} ${NGINX_5XX_FILTER} | sort by (_time desc) | limit 20`
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
          chartType: 'nginxTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 160 },
            { title: '级别', dataIndex: 'nginx.error.level', key: 'nginx.error.level', width: 90, render: renderWebLevel },
            { title: '连接 ID', dataIndex: 'nginx.error.connection_id', key: 'nginx.error.connection_id', width: 110 },
            { title: '消息摘要', dataIndex: 'nginx.error.message', key: 'nginx.error.message', width: 360 }
          ],
          dataSourceParams: {
            searchQuery: `${NGINX_ERROR_BASE} ${NGINX_LEVEL}:*`,
            query: `${NGINX_ERROR_BASE} ${NGINX_LEVEL}:* | sort by (_time desc) | limit 20`
          }
        }
      }
    ]
  };
};
