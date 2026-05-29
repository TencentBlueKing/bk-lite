import { useTranslation } from '@/utils/i18n';
import { Progress } from 'antd';
import { v4 as uuidv4 } from 'uuid';

const SYSLOG_BASE =
  'collect_type:"syslog" service.name:"bk-lite-analysis-sample" event.dataset:"syslog"';
const SYSLOG_HOST = 'host.name';
const SYSLOG_APP = 'appname';
const SYSLOG_FACILITY = 'facility';
const SYSLOG_SEVERITY = 'severity';
const TIME_BUCKET = '${_time}';
const SYSLOG_HIGH_FILTER =
  'severity:"critical" OR severity:"error" OR severity:"alert" OR severity:"emergency" OR severity:"crit" OR severity:"err"';

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

const SYSLOG_SEVERITY_META: Record<string, { label: string; text: string; background: string }> = {
  emergency: { label: 'Emergency', text: '#cf1322', background: 'rgba(207, 19, 34, 0.12)' },
  alert: { label: 'Alert', text: '#f5222d', background: 'rgba(245, 34, 45, 0.12)' },
  critical: { label: 'Critical', text: '#fa541c', background: 'rgba(250, 84, 28, 0.12)' },
  crit: { label: 'Critical', text: '#fa541c', background: 'rgba(250, 84, 28, 0.12)' },
  error: { label: 'Error', text: '#ff4d4f', background: 'rgba(255, 77, 79, 0.12)' },
  err: { label: 'Error', text: '#ff4d4f', background: 'rgba(255, 77, 79, 0.12)' },
  warning: { label: 'Warning', text: '#faad14', background: 'rgba(250, 173, 20, 0.14)' },
  warn: { label: 'Warning', text: '#faad14', background: 'rgba(250, 173, 20, 0.14)' },
  notice: { label: 'Notice', text: '#13c2c2', background: 'rgba(19, 194, 194, 0.12)' },
  info: { label: 'Info', text: '#1677ff', background: 'rgba(22, 119, 255, 0.12)' },
  debug: { label: 'Debug', text: '#8c8c8c', background: 'rgba(140, 140, 140, 0.12)' }
};

const renderSyslogSeverity = (value: unknown) => {
  const key = String(value || '').trim().toLowerCase();
  const meta = SYSLOG_SEVERITY_META[key] || {
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

export const useSyslogDashboard = () => {
  const { t } = useTranslation();

  return {
    name: 'Syslog 日志分析仪表盘',
    desc: '',
    id: 'mock-syslog',
    category: 'middleware',
    categoryName: t('log.analysis.category.middleware'),
    collectTypeName: 'syslog',
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
        description: '当前时间范围内 Syslog 日志总数',
        valueConfig: {
          chartType: 'syslogKpiCard',
          dataSource: 1,
          color: 'primary',
          displayMaps: { type: 'single', key: '_time', value: 'total_count' },
          dataSourceParams: {
            searchQuery: SYSLOG_BASE,
            query: `${SYSLOG_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 3,
        y: 0,
        i: uuidv4(),
        name: '高危日志数',
        description: '当前时间范围内高严重级别日志总数',
        valueConfig: {
          chartType: 'syslogKpiCard',
          dataSource: 1,
          color: 'danger',
          displayMaps: { type: 'single', key: '_time', value: 'high_count' },
          dataSourceParams: {
            searchQuery: `${SYSLOG_BASE} (${SYSLOG_HIGH_FILTER})`,
            query: `${SYSLOG_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${SYSLOG_HIGH_FILTER}) as high_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: '活跃主机数',
        description: '在该时间范围内产生日志的主机数量',
        valueConfig: {
          chartType: 'syslogKpiCard',
          dataSource: 1,
          color: 'accent',
          metricMode: 'latest',
          displayMaps: { type: 'single', key: '_time', value: 'active_host_count' },
          dataSourceParams: {
            searchQuery: `${SYSLOG_BASE} ${SYSLOG_HOST}:*`,
            query: `${SYSLOG_BASE} ${SYSLOG_HOST}:* | stats by (_time:${TIME_BUCKET},${SYSLOG_HOST}) count() as host_count | stats by (_time) count() as active_host_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: '活跃应用数',
        description: '在该时间范围内产生日志的应用数量',
        valueConfig: {
          chartType: 'syslogKpiCard',
          dataSource: 1,
          color: 'info',
          metricMode: 'latest',
          displayMaps: { type: 'single', key: '_time', value: 'active_app_count' },
          dataSourceParams: {
            searchQuery: `${SYSLOG_BASE} ${SYSLOG_APP}:*`,
            query: `${SYSLOG_BASE} ${SYSLOG_APP}:* | stats by (_time:${TIME_BUCKET},${SYSLOG_APP}) count() as app_count | stats by (_time) count() as active_app_count`
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
          chartType: 'syslogTrend',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: SYSLOG_BASE,
            query:
              `${SYSLOG_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count, count() if (${SYSLOG_HIGH_FILTER}) as high_count`
          }
        }
      },
      {
        h: 3,
        w: 5,
        x: 7,
        y: 2,
        i: uuidv4(),
        name: '严重级别分布',
        valueConfig: {
          chartType: 'syslogPie',
          dataSource: 1,
          displayMaps: { key: 'severity', value: 'count' },
          dataSourceParams: {
            searchQuery: `${SYSLOG_BASE} ${SYSLOG_SEVERITY}:*`,
            query: `${SYSLOG_BASE} ${SYSLOG_SEVERITY}:* | stats by (${SYSLOG_SEVERITY}) count() as count | sort by (count desc)`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: 'Top 高危主机',
        valueConfig: {
          chartType: 'syslogTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: '主机', dataIndex: 'host.name', key: 'host.name', width: 150 },
            { title: '总日志数 (条)', dataIndex: 'total_count', key: 'total_count', width: 110 },
            { title: '高危日志数 (条)', dataIndex: 'high_count', key: 'high_count', width: 120 },
            { title: '高危占比', dataIndex: 'ratio', key: 'ratio', width: 140, render: renderRatioProgress }
          ],
          dataSourceParams: {
            searchQuery: `${SYSLOG_BASE} ${SYSLOG_HOST}:*`,
            query: `${SYSLOG_BASE} ${SYSLOG_HOST}:* | stats by (${SYSLOG_HOST}) count() as total_count, count() if (${SYSLOG_HIGH_FILTER}) as high_count | sort by (high_count desc, total_count desc) | limit 10`,
            transformMode: 'highRiskRatio'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: 'Top 高危应用',
        valueConfig: {
          chartType: 'syslogTable',
          dataSource: 1,
          showIndex: true,
          columns: [
            { title: '应用', dataIndex: 'appname', key: 'appname', width: 150 },
            { title: '总日志数 (条)', dataIndex: 'total_count', key: 'total_count', width: 110 },
            { title: '高危日志数 (条)', dataIndex: 'high_count', key: 'high_count', width: 120 },
            { title: '高危占比', dataIndex: 'ratio', key: 'ratio', width: 140, render: renderRatioProgress }
          ],
          dataSourceParams: {
            searchQuery: `${SYSLOG_BASE} ${SYSLOG_APP}:*`,
            query: `${SYSLOG_BASE} ${SYSLOG_APP}:* | stats by (${SYSLOG_APP}) count() as total_count, count() if (${SYSLOG_HIGH_FILTER}) as high_count | sort by (high_count desc, total_count desc) | limit 10`,
            transformMode: 'highRiskRatio'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 5,
        i: uuidv4(),
        name: 'Facility 分布',
        valueConfig: {
          chartType: 'dockerBar',
          dataSource: 1,
          barColor: '#1677ff',
          displayMaps: { key: 'facility', value: 'count' },
          dataSourceParams: {
            searchQuery: `${SYSLOG_BASE} ${SYSLOG_FACILITY}:*`,
            query: `${SYSLOG_BASE} ${SYSLOG_FACILITY}:* | stats by (${SYSLOG_FACILITY}) count() as count | sort by (count desc) | limit 10`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: '最近高危日志',
        valueConfig: {
          chartType: 'syslogTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 160 },
            { title: '主机', dataIndex: 'host.name', key: 'host.name', width: 140 },
            { title: '应用', dataIndex: 'appname', key: 'appname', width: 120 },
            { title: 'Facility', dataIndex: 'facility', key: 'facility', width: 90 },
            { title: 'Severity', dataIndex: 'severity', key: 'severity', width: 96, render: renderSyslogSeverity },
            { title: '进程ID', dataIndex: 'procid', key: 'procid', width: 90 },
            { title: '来源IP', dataIndex: 'source_ip', key: 'source_ip', width: 110 },
            { title: '消息摘要', dataIndex: 'message', key: 'message', width: 320 }
          ],
          dataSourceParams: {
            searchQuery: `${SYSLOG_BASE} (${SYSLOG_HIGH_FILTER})`,
            query: `${SYSLOG_BASE} (${SYSLOG_HIGH_FILTER}) | sort by (_time desc) | limit 20`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 6,
        y: 8,
        i: uuidv4(),
        name: '最近 Syslog 明细',
        valueConfig: {
          chartType: 'syslogTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 160 },
            { title: '主机', dataIndex: 'host.name', key: 'host.name', width: 140 },
            { title: '应用', dataIndex: 'appname', key: 'appname', width: 120 },
            { title: 'Facility', dataIndex: 'facility', key: 'facility', width: 90 },
            { title: 'Severity', dataIndex: 'severity', key: 'severity', width: 96, render: renderSyslogSeverity },
            { title: '进程ID', dataIndex: 'procid', key: 'procid', width: 90 },
            { title: '来源IP', dataIndex: 'source_ip', key: 'source_ip', width: 110 },
            { title: '消息摘要', dataIndex: 'message', key: 'message', width: 320 }
          ],
          dataSourceParams: {
            searchQuery: SYSLOG_BASE,
            query: `${SYSLOG_BASE} | sort by (_time desc) | limit 20`
          }
        }
      }
    ]
  };
};
