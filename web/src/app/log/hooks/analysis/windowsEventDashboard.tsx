import { useTranslation } from '@/utils/i18n';
import { v4 as uuidv4 } from 'uuid';

const WIN_BASE =
  'collect_type:"winlogbeat" service.name:"bk-lite-analysis-sample" event.dataset:"winlogbeat"';
const WIN_EVENT_ID = 'winlog.event_id';
const WIN_CHANNEL = 'winlog.channel';
const WIN_PROVIDER = 'winlog.provider_name';
const WIN_HOST = 'winlog.computer_name';
const WIN_LEVEL = 'log.level';
const TIME_BUCKET = '${_time}';
const SECURITY_EVENT_FILTER =
  'winlog.event_id:"4624" OR winlog.event_id:"4625" OR winlog.event_id:"1102"';
const ABNORMAL_EVENT_FILTER =
  'winlog.event_id:"4625" OR winlog.event_id:"7031" OR winlog.event_id:"1000" OR winlog.event_id:"1102"';

const renderTag = (
  label: unknown,
  textColor: string,
  backgroundColor: string,
  minWidth?: number
) => (
  <span
    className="inline-flex items-center justify-center rounded px-2 py-0.5 text-xs font-medium"
    style={{ color: textColor, backgroundColor, minWidth }}
  >
    {String(label || '--')}
  </span>
);

const renderEventLevel = (value: unknown) => {
  const raw = String(value || '').trim().toLowerCase();
  const text =
    raw === 'error' ? '错误' : raw === 'warning' ? '警告' : raw === 'information' ? '信息' : raw || '--';
  const colorMap: Record<string, { text: string; background: string }> = {
    错误: { text: '#f5222d', background: 'rgba(245, 34, 45, 0.12)' },
    警告: { text: '#fa8c16', background: 'rgba(250, 140, 22, 0.12)' },
    信息: { text: '#1677ff', background: 'rgba(22, 119, 255, 0.12)' }
  };
  const meta = colorMap[text] || {
    text: '#5a6d7f',
    background: 'rgba(90, 109, 127, 0.12)'
  };

  return renderTag(text || '--', meta.text, meta.background, 52);
};

export const useWindowsEventDashboard = () => {
  const { t } = useTranslation();

  return {
    name: 'Windows 事件日志分析',
    desc: '',
    id: 'mock-winlogbeat',
    category: 'middleware',
    categoryName: t('log.analysis.category.middleware'),
    collectTypeName: 'winlogbeat',
    filters: { group: true, instance: true },
    other: {},
    view_sets: [
      {
        h: 2,
        w: 3,
        x: 0,
        y: 0,
        i: uuidv4(),
        name: '总事件数',
        description: '所有通道事件总数',
        valueConfig: {
          chartType: 'windowsEventKpiCard',
          dataSource: 1,
          color: 'primary',
          displayMaps: { type: 'single', key: '_time', value: 'total_count' },
          dataSourceParams: {
            searchQuery: WIN_BASE,
            query: `${WIN_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 3,
        y: 0,
        i: uuidv4(),
        name: '关键安全事件数',
        description: '按固定事件 ID 集合统计的关键安全事件数',
        valueConfig: {
          chartType: 'windowsEventKpiCard',
          dataSource: 1,
          color: 'danger',
          displayMaps: { type: 'single', key: '_time', value: 'high_risk_count' },
          dataSourceParams: {
            searchQuery: `${WIN_BASE} (${SECURITY_EVENT_FILTER})`,
            query: `${WIN_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${SECURITY_EVENT_FILTER}) as high_risk_count`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 6,
        y: 0,
        i: uuidv4(),
        name: '登录失败数',
        description: '事件 ID 4625 统计',
        valueConfig: {
          chartType: 'windowsEventKpiCard',
          dataSource: 1,
          color: 'accent',
          displayMaps: { type: 'single', key: '_time', value: 'login_fail' },
          dataSourceParams: {
            searchQuery: `${WIN_BASE} ${WIN_EVENT_ID}:"4625"`,
            query: `${WIN_BASE} | stats by (_time:${TIME_BUCKET}) count() if (${WIN_EVENT_ID}:"4625") as login_fail`
          }
        }
      },
      {
        h: 2,
        w: 3,
        x: 9,
        y: 0,
        i: uuidv4(),
        name: '活跃主机数',
        description: '产生事件的主机数量',
        valueConfig: {
          chartType: 'windowsEventKpiCard',
          dataSource: 1,
          color: 'info',
          metricMode: 'latest',
          displayMaps: { type: 'single', key: '_time', value: 'active_host_count' },
          dataSourceParams: {
            searchQuery: `${WIN_BASE} ${WIN_HOST}:*`,
            query: `${WIN_BASE} ${WIN_HOST}:* | stats by (_time:${TIME_BUCKET},${WIN_HOST}) count() as host_count | stats by (_time) count() as active_host_count`
          }
        }
      },
      {
        h: 3,
        w: 7,
        x: 0,
        y: 2,
        i: uuidv4(),
        name: '事件量趋势',
        valueConfig: {
          chartType: 'windowsEventTrend',
          dataSource: 1,
          dataSourceParams: {
            searchQuery: WIN_BASE,
            query:
              `${WIN_BASE} | stats by (_time:${TIME_BUCKET}) count() as total_count, count() if (${SECURITY_EVENT_FILTER}) as security_count, count() if (${WIN_LEVEL}:"warning" OR ${WIN_LEVEL}:"error") as warning_count, count() if (${WIN_EVENT_ID}:"4625") as login_fail`
          }
        }
      },
      {
        h: 3,
        w: 5,
        x: 7,
        y: 2,
        i: uuidv4(),
        name: '通道分布',
        valueConfig: {
          chartType: 'windowsEventPie',
          dataSource: 1,
          displayMaps: { key: 'winlog.channel', value: 'count' },
          dataSourceParams: {
            searchQuery: `${WIN_BASE} ${WIN_CHANNEL}:*`,
            query: `${WIN_BASE} ${WIN_CHANNEL}:* | stats by (${WIN_CHANNEL}) count() as count | sort by (count desc)`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 0,
        y: 5,
        i: uuidv4(),
        name: 'Top 关键事件 ID',
        valueConfig: {
          chartType: 'windowsEventTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '事件 ID', dataIndex: 'event_id', key: 'event_id', width: 90 },
            { title: '事件名称', dataIndex: 'event_name', key: 'event_name', width: 120 },
            { title: '事件数', dataIndex: 'count', key: 'count', width: 100 },
            { title: '占比', dataIndex: 'ratio', key: 'ratio', width: 80 }
          ],
          dataSourceParams: {
            searchQuery: `${WIN_BASE} (${SECURITY_EVENT_FILTER})`,
            query:
              `${WIN_BASE} (${SECURITY_EVENT_FILTER}) | stats by (${WIN_EVENT_ID}) count() as count | sort by (count desc) | limit 10`,
            transformMode: 'windowsEventIds'
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 4,
        y: 5,
        i: uuidv4(),
        name: 'Top 异常主机',
        valueConfig: {
          chartType: 'windowsEventTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '主机', dataIndex: 'winlog.computer_name', key: 'winlog.computer_name', width: 120 },
            { title: '异常事件数', dataIndex: 'abnormal_count', key: 'abnormal_count', width: 100 },
            { title: '登录失败数', dataIndex: 'login_fail_count', key: 'login_fail_count', width: 100 },
            { title: '最后发生时间', dataIndex: 'last_time', key: 'last_time', width: 166 }
          ],
          dataSourceParams: {
            searchQuery: `${WIN_BASE} ${WIN_HOST}:*`,
            query:
              `${WIN_BASE} ${WIN_HOST}:* | stats by (${WIN_HOST}) count() if (${ABNORMAL_EVENT_FILTER}) as abnormal_count, count() if (${WIN_EVENT_ID}:"4625") as login_fail_count, max(_time) as last_time | sort by (abnormal_count desc, login_fail_count desc) | limit 10`
          }
        }
      },
      {
        h: 3,
        w: 4,
        x: 8,
        y: 5,
        i: uuidv4(),
        name: 'Top Provider',
        valueConfig: {
          chartType: 'windowsEventBar',
          dataSource: 1,
          direction: 'horizontal',
          displayMaps: { key: 'winlog.provider_name', value: 'count' },
          dataSourceParams: {
            searchQuery: `${WIN_BASE} ${WIN_PROVIDER}:*`,
            query: `${WIN_BASE} ${WIN_PROVIDER}:* | stats by (${WIN_PROVIDER}) count() as count | sort by (count desc) | limit 10`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 0,
        y: 8,
        i: uuidv4(),
        name: '最近关键安全事件',
        valueConfig: {
          chartType: 'windowsEventTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 176 },
            { title: '主机', dataIndex: 'winlog.computer_name', key: 'winlog.computer_name', width: 120 },
            { title: '用户', dataIndex: 'winlog.user.name', key: 'winlog.user.name', width: 92 },
            { title: '事件 ID', dataIndex: 'winlog.event_id', key: 'winlog.event_id', width: 80 },
            { title: '通道', dataIndex: 'winlog.channel', key: 'winlog.channel', width: 96 },
            { title: 'Provider', dataIndex: 'winlog.provider_name', key: 'winlog.provider_name', width: 180 },
            { title: '消息摘要', dataIndex: 'message', key: 'message', width: 240 }
          ],
          dataSourceParams: {
            searchQuery: `${WIN_BASE} (${SECURITY_EVENT_FILTER})`,
            query: `${WIN_BASE} (${SECURITY_EVENT_FILTER}) | sort by (_time desc) | limit 20`
          }
        }
      },
      {
        h: 4,
        w: 6,
        x: 6,
        y: 8,
        i: uuidv4(),
        name: '最近系统与应用异常',
        valueConfig: {
          chartType: 'windowsEventTable',
          dataSource: 1,
          showIndex: false,
          columns: [
            { title: '时间', dataIndex: '@timestamp', key: '@timestamp', width: 176 },
            { title: '主机', dataIndex: 'winlog.computer_name', key: 'winlog.computer_name', width: 120 },
            { title: '通道', dataIndex: 'winlog.channel', key: 'winlog.channel', width: 90 },
            { title: '级别', dataIndex: 'log.level', key: 'log.level', width: 80, render: renderEventLevel },
            { title: 'Provider', dataIndex: 'winlog.provider_name', key: 'winlog.provider_name', width: 180 },
            { title: '事件 ID', dataIndex: 'winlog.event_id', key: 'winlog.event_id', width: 86 },
            { title: '消息摘要', dataIndex: 'message', key: 'message', width: 250 }
          ],
          dataSourceParams: {
            searchQuery: `${WIN_BASE} (${ABNORMAL_EVENT_FILTER})`,
            query: `${WIN_BASE} (${ABNORMAL_EVENT_FILTER}) | sort by (_time desc) | limit 20`
          }
        }
      }
    ]
  };
};
