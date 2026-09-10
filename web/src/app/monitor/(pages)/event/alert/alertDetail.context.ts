import type { AiContextSection, AiPageContext } from '@/components/ai-page-context/types';
import { buildAlertDimensionDisplayItems } from './alertDimensionUtils';

export const ALERT_DETAIL_EVENT_LIMIT = 30;

export interface AlertDetailContextLabels {
  level: (value?: string) => string;
  state: (value?: string) => string;
  alertType: (value?: string) => string;
  action: (value?: string) => string;
  formatTime: (value?: string) => string;
  formatValue: (metric: unknown, value: unknown) => string;
  notice: (noticed?: boolean) => string;
  formatPerson: (value?: unknown) => string;
  formatUnit: (unitId?: string) => string;
}

export interface AlertDetailContextInput {
  visible: boolean;
  pageLoading?: boolean;
  eventLoading?: boolean;
  formData?: Record<string, any>;
  eventData?: Array<Record<string, any>>;
  trapData?: Record<string, any>;
  chartUnit?: string;
  labels: AlertDetailContextLabels;
}

const cleanLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

const eventTimeValue = (item: Record<string, any>): number => {
  const raw = item.event_time;
  const ts = raw ? Date.parse(String(raw)) : Number.NaN;
  return Number.isFinite(ts) ? ts : 0;
};

const formatNotifiers = (
  form: Record<string, any>,
  formatPerson: (value?: unknown) => string,
): string => {
  if (Array.isArray(form.notice_users_display) && form.notice_users_display.length) {
    return form.notice_users_display.map((item: unknown) => String(item)).filter(Boolean).join(',');
  }
  const users = form.notice_users || form.policy?.notice_users;
  if (!Array.isArray(users) || !users.length) return '';
  return users.map((item: unknown) => formatPerson(item)).filter(Boolean).join(',');
};

export function buildAlertDetailPageContext(input: AlertDetailContextInput): Partial<AiPageContext> {
  if (!input.visible) return { sections: [], images: [] };
  const form = input.formData || {};
  const labels = input.labels;
  const identity = [
    '正在查看告警详情',
    form.id != null ? `告警 id: ${form.id}` : '',
    form.content ? `告警: ${form.content}` : '',
    `级别: ${labels.level(form.level)}`,
    `状态: ${labels.state(form.status)}`,
    `类型: ${labels.alertType(form.alert_type)}`,
    form.updated_at ? `时间: ${labels.formatTime(form.updated_at)}` : '',
    form.monitor_instance_name ? `资产: ${form.monitor_instance_name}` : '',
    input.pageLoading ? '详情加载中' : '',
  ].filter(Boolean);

  const dimensions = buildAlertDimensionDisplayItems(form.metric?.dimensions, form.dimensions)
    .map((item) => `${item.label}: ${item.value}`);
  const trapEntries = Object.entries(input.trapData || {}).map(([key, value]) => {
    const text = Array.isArray(value) ? String(value[0]?.[1] ?? '--') : String(value ?? '--');
    return `${key}: ${text}`;
  });
  const unitName = labels.formatUnit(input.chartUnit);
  const metricName = form.metric?.display_name
    ? (unitName ? `指标: ${form.metric.display_name}（${unitName}）` : `指标: ${form.metric.display_name}`)
    : '';
  const notifiers = formatNotifiers(form, labels.formatPerson);
  const operator = labels.formatPerson(form.operator);
  const fieldLines = [
    ...dimensions,
    form.policy?.name ? `策略: ${form.policy.name}` : '',
    form.policy ? `通知: ${labels.notice(Boolean(form.policy.notice))}` : '',
    notifiers ? `通知人: ${notifiers}` : '',
    operator && operator !== '--' ? `操作人: ${operator}` : '',
    form.end_event_time ? `结束时间: ${labels.formatTime(form.end_event_time)}` : '',
    metricName,
    ...trapEntries,
  ].filter(Boolean);

  const allEvents = [...(input.eventData || [])].sort((left, right) => eventTimeValue(right) - eventTimeValue(left));
  const attached = allEvents.slice(0, ALERT_DETAIL_EVENT_LIMIT);
  const eventLines = input.eventLoading
    ? ['事件加载中']
    : allEvents.length
      ? [
        `共 ${allEvents.length} 条，已附最近 ${attached.length} 条`,
        ...attached.map((item) => cleanLabel([
          labels.formatTime(item.event_time),
          labels.action(item.action),
          labels.level(item.level),
          item.content || form.metric?.display_name || '',
          labels.formatValue(form.metric, item.value),
        ].filter(Boolean).join(' '))),
      ]
      : ['暂无事件'];

  const sections: AiContextSection[] = [
    { id: 'alert-detail-identity', label: '当前告警详情', content: identity.join('\n'), priority: 10 },
    ...(fieldLines.length
      ? [{ id: 'alert-detail-fields', label: '详情字段', content: fieldLines.join('\n'), priority: 9 }]
      : []),
    { id: 'alert-detail-events', label: '事件', content: eventLines.join('\n'), priority: 8 },
  ];
  return { app: 'monitor', sections, images: [] };
}
