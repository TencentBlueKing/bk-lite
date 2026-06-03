import { useTranslation } from '@/utils/i18n';
import { Progress } from 'antd';
import { v4 as uuidv4 } from 'uuid';

const MONGO_BASE =
  'collect_type:"mongodb" service.name:"bk-lite-analysis-sample" event.dataset:"mongodb.log"';
const MONGO_SEVERITY = 'mongodb.log.severity';
const MONGO_COMPONENT = 'mongodb.log.component';
const MONGO_CONTEXT = 'mongodb.log.context';
const MONGO_MESSAGE = 'mongodb.log.message';
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
        strokeColor="#f5222d"
        trailColor="rgba(0, 0, 0, 0.06)"
        className="mb-0 min-w-0 flex-1"
      />
      <span className="min-w-[44px] text-xs text-[var(--color-text-2)]">
        {String(value || '--')}
      </span>
    </div>
  );
};

const renderMongoSeverity = (value: unknown) => {
  const text = String(value || '').toUpperCase();
  const colorMap: Record<string, { text: string; background: string }> = {
    ERROR: { text: '#f5222d', background: 'rgba(245, 34, 45, 0.12)' },
    WARN: { text: '#fa8c16', background: 'rgba(250, 140, 22, 0.12)' },
    WARNING: { text: '#fa8c16', background: 'rgba(250, 140, 22, 0.12)' },
    FATAL: { text: '#722ed1', background: 'rgba(114, 46, 209, 0.12)' },
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

export const useMongodbDashboard = () => {
  const { t } = useTranslation();

  return {
    name: 'MongoDB 日志分析',
    desc: '',
    id: 'mock-mongodb',
    category: 'middleware',
    categoryName: t('log.analysis.category.middleware'),
    collectTypeName: 'mongodb',
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
        description: '当前时间范围内 MongoDB 日志总数',
        valueConfig: {
          chartType: 'mongodbKpiCard',
          dataSource: 1,
          color: 'primary',
          displayMaps: { type: 'single', key: '_time', value: 'total_count' },
          dataSourceParams: {
            searchQuery: MONGO_BASE,
            query: `${MONGO_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count`
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
          chartType: 'mongodbKpiCard',
          dataSource: 1,
          color: 'danger',
          displayMaps: { type: 'single', key: '_time', value: 'error_count' },
          dataSourceParams: {
            searchQuery: `${MONGO_BASE} (${MONGO_SEVERITY}:"ERROR" OR ${MONGO_SEVERITY}:"FATAL")`,
            query:
              `${MONGO_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${MONGO_SEVERITY}:"ERROR" OR ${MONGO_SEVERITY}:"FATAL") as error_count`
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
          chartType: 'mongodbKpiCard',
          dataSource: 1,
          color: 'accent',
          displayMaps: { type: 'single', key: '_time', value: 'warning_count' },
          dataSourceParams: {
            searchQuery: `${MONGO_BASE} (${MONGO_SEVERITY}:"WARN" OR ${MONGO_SEVERITY}:"WARNING")`,
            query:
              `${MONGO_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${MONGO_SEVERITY}:"WARN" OR ${MONGO_SEVERITY}:"WARNING") as warning_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: '涉及实例数',
        description: '当前时间范围内出现日志的 MongoDB 实例数',
        valueConfig: {
          chartType: 'mongodbKpiCard',
          dataSource: 1,
          color: 'info',
          metricMode: 'latest',
          displayMaps: { type: 'single', key: '_time', value: 'instance_count' },
          dataSourceParams: {
            searchQuery: `${MONGO_BASE} instance_id:*`,
            query:
              `${MONGO_BASE} instance_id:* | stats by (_time:${TIME_BUCKET},instance_id) count() as log_count | stats by (_time) count() as instance_count`
          }
        }
      },
      {
        h: 3,
        w: 7,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: '日志量与高危日志趋势',
        valueConfig: {
          chartType: 'mongodbTrend',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: MONGO_BASE,
            query:
              `${MONGO_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count, count() if (${MONGO_SEVERITY}:"ERROR" OR ${MONGO_SEVERITY}:"FATAL") as error_count, count() if (${MONGO_SEVERITY}:"WARN" OR ${MONGO_SEVERITY}:"WARNING") as warning_count, count() if (${MONGO_MESSAGE}:re(".*Slow.*") OR ${MONGO_MESSAGE}:re(".*slow.*")) as slow_count`
          }
        }
      },
      {
        h: 3,
        w: 5,
        x: 7,
        y: 2,
        i: uuidv4(),
        name: '日志级别分布',
        valueConfig: {
          chartType: 'mongodbPie',
          dataSource: 1,
          displayMaps: { key: 'mongodb.log.severity', value: 'count' },
          dataSourceParams: {
            searchQuery: `${MONGO_BASE} ${MONGO_SEVERITY}:*`,
            query: `${MONGO_BASE} ${MONGO_SEVERITY}:* | stats by (${MONGO_SEVERITY}) count() as count | sort by (count desc)`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: 'Top 异常组件',
        valueConfig: {
          chartType: 'mongodbTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: '组件', dataIndex: 'mongodb.log.component', key: 'mongodb.log.component', width: 160 },
            { title: 'Error / Fatal 日志数', dataIndex: 'count', key: 'count', width: 150 },
            { title: '占比', dataIndex: 'ratio', key: 'ratio', width: 140, render: renderRatioProgress }
          ],
          dataSourceParams: {
            searchQuery: `${MONGO_BASE} (${MONGO_SEVERITY}:"ERROR" OR ${MONGO_SEVERITY}:"FATAL") ${MONGO_COMPONENT}:*`,
            query:
              `${MONGO_BASE} (${MONGO_SEVERITY}:"ERROR" OR ${MONGO_SEVERITY}:"FATAL") ${MONGO_COMPONENT}:* | stats by (${MONGO_COMPONENT}) count() as count | sort by (count desc) | limit 5`,
            transformMode: 'mongoTopComponents'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: 'Top 错误消息',
        valueConfig: {
          chartType: 'mongodbTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: '错误消息', dataIndex: 'mongodb.log.message', key: 'mongodb.log.message', width: 200 },
            { title: '出现次数', dataIndex: 'count', key: 'count', width: 110 },
            { title: '占比', dataIndex: 'ratio', key: 'ratio', width: 140, render: renderRatioProgress }
          ],
          dataSourceParams: {
            searchQuery: `${MONGO_BASE} (${MONGO_SEVERITY}:"ERROR" OR ${MONGO_SEVERITY}:"FATAL") ${MONGO_MESSAGE}:*`,
            query:
              `${MONGO_BASE} (${MONGO_SEVERITY}:"ERROR" OR ${MONGO_SEVERITY}:"FATAL") ${MONGO_MESSAGE}:* | stats by (${MONGO_MESSAGE}) count() as count | sort by (count desc) | limit 5`,
            transformMode: 'mongoTopMessages'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 5,
        i: uuidv4(),
        name: 'Top 上下文',
        valueConfig: {
          chartType: 'mongodbTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: '上下文', dataIndex: 'mongodb.log.context', key: 'mongodb.log.context', width: 160 },
            { title: '事件数', dataIndex: 'count', key: 'count', width: 110 },
            { title: '占比', dataIndex: 'ratio', key: 'ratio', width: 140, render: renderRatioProgress }
          ],
          dataSourceParams: {
            searchQuery: `${MONGO_BASE} ${MONGO_CONTEXT}:*`,
            query:
              `${MONGO_BASE} ${MONGO_CONTEXT}:* | stats by (${MONGO_CONTEXT}) count() as count | sort by (count desc) | limit 5`,
            transformMode: 'mongoTopContexts'
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: '最近错误/告警事件',
        valueConfig: {
          chartType: 'mongodbTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 168 },
            { title: '实例', dataIndex: 'instance_id', key: 'instance_id', width: 160 },
            { title: '级别', dataIndex: 'mongodb.log.severity', key: 'mongodb.log.severity', width: 90, render: renderMongoSeverity },
            { title: '组件', dataIndex: 'mongodb.log.component', key: 'mongodb.log.component', width: 140 },
            { title: '摘要', dataIndex: 'mongodb.log.message', key: 'mongodb.log.message', width: 320 }
          ],
          dataSourceParams: {
            searchQuery: `${MONGO_BASE} (${MONGO_SEVERITY}:"ERROR" OR ${MONGO_SEVERITY}:"FATAL" OR ${MONGO_SEVERITY}:"WARN" OR ${MONGO_SEVERITY}:"WARNING")`,
            query:
              `${MONGO_BASE} (${MONGO_SEVERITY}:"ERROR" OR ${MONGO_SEVERITY}:"FATAL" OR ${MONGO_SEVERITY}:"WARN" OR ${MONGO_SEVERITY}:"WARNING") | sort by (_time desc) | limit 20`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 6,
        y: 8,
        i: uuidv4(),
        name: '最近组件事件明细',
        valueConfig: {
          chartType: 'mongodbTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 168 },
            { title: '实例', dataIndex: 'instance_id', key: 'instance_id', width: 160 },
            { title: '级别', dataIndex: 'mongodb.log.severity', key: 'mongodb.log.severity', width: 90, render: renderMongoSeverity },
            { title: '组件', dataIndex: 'mongodb.log.component', key: 'mongodb.log.component', width: 140 },
            { title: '上下文', dataIndex: 'mongodb.log.context', key: 'mongodb.log.context', width: 140 },
            { title: '摘要', dataIndex: 'mongodb.log.message', key: 'mongodb.log.message', width: 280 }
          ],
          dataSourceParams: {
            searchQuery: `${MONGO_BASE} ${MONGO_COMPONENT}:*`,
            query: `${MONGO_BASE} ${MONGO_COMPONENT}:* | sort by (_time desc) | limit 20`
          }
        }
      }
    ]
  };
};
