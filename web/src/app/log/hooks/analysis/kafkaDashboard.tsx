import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';

const KAFKA_BASE =
  'collect_type:"kafka" service.name:"bk-lite-analysis-sample" event.dataset:"kafka.log"';
const KAFKA_LEVEL = 'kafka.log.level';
const KAFKA_COMPONENT = 'kafka.log.component';
const KAFKA_MESSAGE = 'kafka.log.message';
const KAFKA_TRACE_CLASS = 'kafka.log.trace.class';
const TIME_BUCKET = '${_time}';

const renderKafkaLevel = (value: unknown) => {
  const text = String(value || '').toUpperCase();
  const colorMap: Record<string, { text: string; background: string }> = {
    ERROR: { text: '#f5222d', background: 'rgba(245, 34, 45, 0.12)' },
    WARN: { text: '#fa8c16', background: 'rgba(250, 140, 22, 0.12)' },
    WARNING: { text: '#fa8c16', background: 'rgba(250, 140, 22, 0.12)' },
    INFO: { text: '#1677ff', background: 'rgba(22, 119, 255, 0.12)' },
    FATAL: { text: '#722ed1', background: 'rgba(114, 46, 209, 0.12)' }
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

export const useKafkaDashboard = () => {
  const { t } = useTranslation();

  return {
    name: 'Kafka 日志分析',
    desc: '',
    id: 'mock-kafka',
    category: 'middleware',
    categoryName: t('log.analysis.category.middleware'),
    collectTypeName: 'kafka',
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
        description: '当前时间范围内 Kafka 日志总数',
        valueConfig: {
          chartType: 'kafkaKpiCard',
          dataSource: 1,
          color: 'primary',
          displayMaps: { type: 'single', key: '_time', value: 'total_count' },
          dataSourceParams: {
            searchQuery: KAFKA_BASE,
            query: `${KAFKA_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count`
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
          chartType: 'kafkaKpiCard',
          dataSource: 1,
          color: 'danger',
          displayMaps: { type: 'single', key: '_time', value: 'error_count' },
          dataSourceParams: {
            searchQuery: `${KAFKA_BASE} (${KAFKA_LEVEL}:"ERROR" OR ${KAFKA_LEVEL}:"FATAL")`,
            query:
              `${KAFKA_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${KAFKA_LEVEL}:"ERROR" OR ${KAFKA_LEVEL}:"FATAL") as error_count`
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
        description: '当前时间范围内 warning 日志总数',
        valueConfig: {
          chartType: 'kafkaKpiCard',
          dataSource: 1,
          color: 'warning',
          displayMaps: { type: 'single', key: '_time', value: 'warning_count' },
          dataSourceParams: {
            searchQuery: `${KAFKA_BASE} (${KAFKA_LEVEL}:"WARN" OR ${KAFKA_LEVEL}:"WARNING")`,
            query:
              `${KAFKA_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${KAFKA_LEVEL}:"WARN" OR ${KAFKA_LEVEL}:"WARNING") as warning_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: '异常堆栈日志数',
        description: '当前时间范围内异常堆栈日志总数',
        valueConfig: {
          chartType: 'kafkaKpiCard',
          dataSource: 1,
          color: 'accent',
          displayMaps: { type: 'single', key: '_time', value: 'stack_count' },
          dataSourceParams: {
            searchQuery: `${KAFKA_BASE} ${KAFKA_TRACE_CLASS}:*`,
            query: `${KAFKA_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${KAFKA_TRACE_CLASS}:*) as stack_count`
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
          chartType: 'kafkaTrend',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: KAFKA_BASE,
            query:
              `${KAFKA_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count, count() if (${KAFKA_LEVEL}:"ERROR" OR ${KAFKA_LEVEL}:"FATAL") as error_count, count() if (${KAFKA_LEVEL}:"WARN" OR ${KAFKA_LEVEL}:"WARNING") as warning_count, count() if (${KAFKA_TRACE_CLASS}:*) as stack_count`
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
          chartType: 'kafkaPie',
          dataSource: 1,
          displayMaps: { key: 'kafka.log.level', value: 'count' },
          dataSourceParams: {
            searchQuery: `${KAFKA_BASE} ${KAFKA_LEVEL}:*`,
            query: `${KAFKA_BASE} ${KAFKA_LEVEL}:* | stats by (${KAFKA_LEVEL}) count() as count | sort by (count desc)`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: 'Top 异常类',
        valueConfig: {
          chartType: 'kafkaBar',
          dataSource: 1,
          direction: 'horizontal',
          displayMaps: { key: 'kafka.log.trace.class', value: 'count' },
          dataSourceParams: {
            searchQuery: `${KAFKA_BASE} ${KAFKA_TRACE_CLASS}:*`,
            query: `${KAFKA_BASE} ${KAFKA_TRACE_CLASS}:* | stats by (${KAFKA_TRACE_CLASS}) count() as count | sort by (count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: 'Top 异常组件',
        valueConfig: {
          chartType: 'kafkaTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: '组件', dataIndex: 'kafka.log.component', key: 'kafka.log.component', width: 180 },
            { title: 'Error / Fatal', dataIndex: 'error_count', key: 'error_count', width: 120 },
            { title: 'Warning', dataIndex: 'warning_count', key: 'warning_count', width: 120 },
            { title: '异常堆栈', dataIndex: 'stack_count', key: 'stack_count', width: 120 }
          ],
          dataSourceParams: {
            searchQuery: `${KAFKA_BASE} ${KAFKA_COMPONENT}:*`,
            query:
              `${KAFKA_BASE} ${KAFKA_COMPONENT}:* | stats by (${KAFKA_COMPONENT}) count() if (${KAFKA_LEVEL}:"ERROR" OR ${KAFKA_LEVEL}:"FATAL") as error_count, count() if (${KAFKA_LEVEL}:"WARN" OR ${KAFKA_LEVEL}:"WARNING") as warning_count, count() if (${KAFKA_TRACE_CLASS}:*) as stack_count | sort by (error_count desc, warning_count desc, stack_count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 5,
        i: uuidv4(),
        name: 'Top 高频错误消息',
        valueConfig: {
          chartType: 'kafkaTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: '错误消息', dataIndex: 'kafka.log.message', key: 'kafka.log.message', width: 340 },
            { title: '出现次数', dataIndex: 'count', key: 'count', width: 110 }
          ],
          dataSourceParams: {
            searchQuery: `${KAFKA_BASE} (${KAFKA_LEVEL}:"ERROR" OR ${KAFKA_LEVEL}:"FATAL" OR ${KAFKA_LEVEL}:"WARN" OR ${KAFKA_LEVEL}:"WARNING") ${KAFKA_MESSAGE}:*`,
            query:
              `${KAFKA_BASE} (${KAFKA_LEVEL}:"ERROR" OR ${KAFKA_LEVEL}:"FATAL" OR ${KAFKA_LEVEL}:"WARN" OR ${KAFKA_LEVEL}:"WARNING") ${KAFKA_MESSAGE}:* | stats by (${KAFKA_MESSAGE}) count() as count | sort by (count desc) | limit 10`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: '最近异常堆栈明细',
        valueConfig: {
          chartType: 'kafkaTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 180 },
            { title: '实例 / Broker', dataIndex: 'instance_id', key: 'instance_id', width: 170 },
            { title: '级别', dataIndex: 'kafka.log.level', key: 'kafka.log.level', width: 90, render: renderKafkaLevel },
            { title: '组件', dataIndex: 'kafka.log.component', key: 'kafka.log.component', width: 140 },
            { title: '异常类型', dataIndex: 'kafka.log.trace.class', key: 'kafka.log.trace.class', width: 220 },
            { title: '消息摘要', dataIndex: 'kafka.log.trace.message', key: 'kafka.log.trace.message', width: 320 }
          ],
          dataSourceParams: {
            searchQuery: `${KAFKA_BASE} ${KAFKA_TRACE_CLASS}:*`,
            query: `${KAFKA_BASE} ${KAFKA_TRACE_CLASS}:* | sort by (_time desc) | limit 20`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 6,
        y: 8,
        i: uuidv4(),
        name: '最近 Error/Warn 日志',
        valueConfig: {
          chartType: 'kafkaTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 180 },
            { title: '实例 / Broker', dataIndex: 'instance_id', key: 'instance_id', width: 170 },
            { title: '级别', dataIndex: 'kafka.log.level', key: 'kafka.log.level', width: 90, render: renderKafkaLevel },
            { title: '组件', dataIndex: 'kafka.log.component', key: 'kafka.log.component', width: 140 },
            { title: '消息摘要', dataIndex: 'kafka.log.message', key: 'kafka.log.message', width: 340 }
          ],
          dataSourceParams: {
            searchQuery: `${KAFKA_BASE} (${KAFKA_LEVEL}:"ERROR" OR ${KAFKA_LEVEL}:"FATAL" OR ${KAFKA_LEVEL}:"WARN" OR ${KAFKA_LEVEL}:"WARNING")`,
            query:
              `${KAFKA_BASE} (${KAFKA_LEVEL}:"ERROR" OR ${KAFKA_LEVEL}:"FATAL" OR ${KAFKA_LEVEL}:"WARN" OR ${KAFKA_LEVEL}:"WARNING") | sort by (_time desc) | limit 20`
          }
        }
      }
    ]
  };
};
