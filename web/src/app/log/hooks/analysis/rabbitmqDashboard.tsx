import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';

const RABBIT_BASE =
  'collect_type:"rabbitmq" service.name:"bk-lite-analysis-sample" event.dataset:"rabbitmq.log"';
const RABBIT_LEVEL = 'rabbitmq.log.level';
const RABBIT_MESSAGE = 'rabbitmq.log.message';
const RABBIT_PID = 'rabbitmq.log.pid';
const TIME_BUCKET = '${_time}';

const RABBIT_KEYWORDS = [
  { key: 'connection', query: `${RABBIT_MESSAGE}:"connection_" OR ${RABBIT_MESSAGE}:"connection "` },
  { key: 'auth', query: `${RABBIT_MESSAGE}:"access_refused" OR ${RABBIT_MESSAGE}:"credentials"` },
  { key: 'channel', query: `${RABBIT_MESSAGE}:"channel_" OR ${RABBIT_MESSAGE}:"channel "` },
  { key: 'queue', query: `${RABBIT_MESSAGE}:"queue_" OR ${RABBIT_MESSAGE}:"queue "` },
  { key: 'heartbeat', query: `${RABBIT_MESSAGE}:"heartbeat"` },
  { key: 'memory', query: `${RABBIT_MESSAGE}:"memory"` },
  { key: 'cluster', query: `${RABBIT_MESSAGE}:"cluster"` }
];

const renderTag = (
  label: unknown,
  textColor: string,
  backgroundColor: string,
  minWidth?: number
) => (
  <span
    className="inline-flex items-center justify-center rounded px-2 py-0.5 text-xs font-medium"
    style={{
      color: textColor,
      backgroundColor,
      minWidth
    }}
  >
    {String(label || '--')}
  </span>
);

const RABBIT_LEVEL_META: Record<
  string,
  { label: string; text: string; background: string }
> = {
  error: { label: 'error', text: '#f5222d', background: 'rgba(245, 34, 45, 0.12)' },
  warning: { label: 'warning', text: '#fa8c16', background: 'rgba(250, 140, 22, 0.12)' },
  info: { label: 'info', text: '#1677ff', background: 'rgba(22, 119, 255, 0.12)' },
  debug: { label: 'debug', text: '#13c2c2', background: 'rgba(19, 194, 194, 0.12)' }
};

const RABBIT_KEYWORD_META: Record<
  string,
  { text: string; background: string }
> = {
  connection: { text: '#1677ff', background: 'rgba(22, 119, 255, 0.12)' },
  auth: { text: '#fa8c16', background: 'rgba(250, 140, 22, 0.12)' },
  channel: { text: '#722ed1', background: 'rgba(114, 46, 209, 0.12)' },
  queue: { text: '#52c41a', background: 'rgba(82, 196, 26, 0.12)' },
  heartbeat: { text: '#9254de', background: 'rgba(146, 84, 222, 0.12)' },
  memory: { text: '#13c2c2', background: 'rgba(19, 194, 194, 0.12)' },
  cluster: { text: '#5a6d7f', background: 'rgba(90, 109, 127, 0.12)' }
};

const renderRabbitLevel = (value: unknown) => {
  const key = String(value || '').trim().toLowerCase();
  const meta = RABBIT_LEVEL_META[key] || {
    label: String(value || '--'),
    text: '#5a6d7f',
    background: 'rgba(90, 109, 127, 0.12)'
  };

  return renderTag(meta.label, meta.text, meta.background);
};

const renderRabbitKeyword = (value: unknown) => {
  const key = String(value || '').trim().toLowerCase();
  const meta = RABBIT_KEYWORD_META[key] || {
    text: '#5a6d7f',
    background: 'rgba(90, 109, 127, 0.12)'
  };

  return renderTag(key || '--', meta.text, meta.background);
};

export const useRabbitmqDashboard = () => {
  const { t } = useTranslation();
  const keywordQuery = RABBIT_KEYWORDS.map(({ query }) => `(${query})`).join(' OR ');

  return {
    name: 'RabbitMQ 日志分析',
    desc: '',
    id: 'mock-rabbitmq',
    category: 'middleware',
    categoryName: t('log.analysis.category.middleware'),
    collectTypeName: 'rabbitmq',
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
        description: '当前时间范围内 RabbitMQ 日志总数',
        valueConfig: {
          chartType: 'rabbitmqKpiCard',
          dataSource: 1,
          color: 'primary',
          displayMaps: { type: 'single', key: '_time', value: 'total_count' },
          dataSourceParams: {
            searchQuery: RABBIT_BASE,
            query: `${RABBIT_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 3,
        y: 0,
        i: uuidv4(),
        name: 'Error 日志数',
        description: '当前时间范围内 Error 日志总数',
        valueConfig: {
          chartType: 'rabbitmqKpiCard',
          dataSource: 1,
          color: 'danger',
          displayMaps: { type: 'single', key: '_time', value: 'error_count' },
          dataSourceParams: {
            searchQuery: `${RABBIT_BASE} ${RABBIT_LEVEL}:"error"`,
            query: `${RABBIT_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${RABBIT_LEVEL}:"error") as error_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: 'Warning 日志数',
        description: '当前时间范围内 Warning 日志总数',
        valueConfig: {
          chartType: 'rabbitmqKpiCard',
          dataSource: 1,
          color: 'warning',
          displayMaps: { type: 'single', key: '_time', value: 'warning_count' },
          dataSourceParams: {
            searchQuery: `${RABBIT_BASE} ${RABBIT_LEVEL}:"warning"`,
            query: `${RABBIT_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${RABBIT_LEVEL}:"warning") as warning_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: '关键异常数',
        description: '按关键词匹配得到的关键异常日志数',
        valueConfig: {
          chartType: 'rabbitmqKpiCard',
          dataSource: 1,
          color: 'accent',
          displayMaps: { type: 'single', key: '_time', value: 'event_count' },
          dataSourceParams: {
            searchQuery: `${RABBIT_BASE} (${keywordQuery})`,
            query: `${RABBIT_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${keywordQuery}) as event_count`
          }
        }
      },
      {
        h: 3,
        w: 8,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: '日志量与错误量趋势',
        valueConfig: {
          chartType: 'rabbitmqTrend',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: RABBIT_BASE,
            query:
              `${RABBIT_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count, count() if (${RABBIT_LEVEL}:"error") as error_count, count() if (${RABBIT_LEVEL}:"warning") as warning_count, count() if (${keywordQuery}) as event_count`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 2,
        i: uuidv4(),
        name: '日志级别分布',
        valueConfig: {
          chartType: 'rabbitmqPie',
          dataSource: 1,
          displayMaps: { key: 'rabbitmq.log.level', value: 'count' },
          dataSourceParams: {
            searchQuery: `${RABBIT_BASE} ${RABBIT_LEVEL}:*`,
            query: `${RABBIT_BASE} ${RABBIT_LEVEL}:* | stats by (${RABBIT_LEVEL}) count() as count | sort by (count desc)`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: 'Top 错误消息摘要',
        valueConfig: {
          chartType: 'rabbitmqTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: '错误消息', dataIndex: 'rabbitmq.log.message', key: 'rabbitmq.log.message', width: 320 },
            { title: '出现次数', dataIndex: 'count', key: 'count', width: 110 }
          ],
          dataSourceParams: {
            searchQuery: `${RABBIT_BASE} (${RABBIT_LEVEL}:"error" OR ${RABBIT_LEVEL}:"warning") ${RABBIT_MESSAGE}:*`,
            query:
              `${RABBIT_BASE} (${RABBIT_LEVEL}:"error" OR ${RABBIT_LEVEL}:"warning") ${RABBIT_MESSAGE}:* | stats by (${RABBIT_MESSAGE}) count() as count | sort by (count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: '关键词分类分布',
        valueConfig: {
          chartType: 'rabbitmqBar',
          dataSource: 1,
          direction: 'horizontal',
          displayMaps: { key: 'keyword_type', value: 'count' },
          dataSourceParams: {
            searchQuery: RABBIT_BASE,
            queries: RABBIT_KEYWORDS.map(({ key, query }) => ({
              key,
              query: `${RABBIT_BASE} (${query}) | stats count() as count`
            })),
            transformMode: 'rabbitmqKeywordCounts'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 5,
        i: uuidv4(),
        name: 'Top 异常进程 PID',
        valueConfig: {
          chartType: 'rabbitmqTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: 'PID', dataIndex: 'rabbitmq.log.pid', key: 'rabbitmq.log.pid', width: 90 },
            { title: 'Error', dataIndex: 'error_count', key: 'error_count', width: 96 },
            { title: 'Warning', dataIndex: 'warning_count', key: 'warning_count', width: 104 },
            { title: '总异常数', dataIndex: 'total_count', key: 'total_count', width: 110 }
          ],
          dataSourceParams: {
            searchQuery: `${RABBIT_BASE} ${RABBIT_PID}:*`,
            query:
              `${RABBIT_BASE} ${RABBIT_PID}:* | stats by (${RABBIT_PID}) count() if (${RABBIT_LEVEL}:"error") as error_count, count() if (${RABBIT_LEVEL}:"warning") as warning_count, count() if (${RABBIT_LEVEL}:"error" OR ${RABBIT_LEVEL}:"warning") as total_count | sort by (total_count desc, error_count desc) | limit 10`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: '最近错误日志',
        valueConfig: {
          chartType: 'rabbitmqTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 176 },
            { title: '级别', dataIndex: 'rabbitmq.log.level', key: 'rabbitmq.log.level', width: 84, render: renderRabbitLevel },
            { title: 'PID', dataIndex: 'rabbitmq.log.pid', key: 'rabbitmq.log.pid', width: 86 },
            { title: '关键词分类', dataIndex: 'keyword_type', key: 'keyword_type', width: 108, render: renderRabbitKeyword },
            { title: '消息摘要', dataIndex: 'rabbitmq.log.message', key: 'rabbitmq.log.message', width: 340 }
          ],
          dataSourceParams: {
            searchQuery: `${RABBIT_BASE} ${RABBIT_LEVEL}:"error"`,
            query: `${RABBIT_BASE} ${RABBIT_LEVEL}:"error" | sort by (_time desc) | limit 20`,
            transformMode: 'rabbitmqRecentEvents'
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 6,
        y: 8,
        i: uuidv4(),
        name: '最近关键日志',
        valueConfig: {
          chartType: 'rabbitmqTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 176 },
            { title: '级别', dataIndex: 'rabbitmq.log.level', key: 'rabbitmq.log.level', width: 84, render: renderRabbitLevel },
            { title: 'PID', dataIndex: 'rabbitmq.log.pid', key: 'rabbitmq.log.pid', width: 86 },
            { title: '关键词分类', dataIndex: 'keyword_type', key: 'keyword_type', width: 108, render: renderRabbitKeyword },
            { title: '消息摘要', dataIndex: 'rabbitmq.log.message', key: 'rabbitmq.log.message', width: 340 }
          ],
          dataSourceParams: {
            searchQuery: `${RABBIT_BASE} (${keywordQuery})`,
            query: `${RABBIT_BASE} (${keywordQuery}) | sort by (_time desc) | limit 20`,
            transformMode: 'rabbitmqRecentEvents'
          }
        }
      }
    ]
  };
};
