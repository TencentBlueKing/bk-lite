import type { AiContextSection, AiPageContext } from '@/components/ai-page-context/types';

export const ALARM_DETAIL_EVENT_LIMIT = 30;

export interface AlarmDetailContextLabels {
  level: (value?: string | number) => string;
  state: (value?: string) => string;
  formatTime: (value?: string) => string;
  notifyStatus: (value?: string) => string;
  objects: (form: Record<string, any>) => string;
}

export interface AlarmDetailContextInput {
  visible: boolean;
  pageLoading?: boolean;
  eventLoading?: boolean;
  formData?: Record<string, any>;
  eventData?: Array<Record<string, any>>;
  eventTotal?: number;
  labels: AlarmDetailContextLabels;
}

const cleanLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

const eventTimeValue = (item: Record<string, any>): number => {
  const raw = item.received_at || item.start_time || item.created_at;
  const ts = raw ? Date.parse(String(raw)) : Number.NaN;
  return Number.isFinite(ts) ? ts : 0;
};

export function buildAlarmDetailPageContext(input: AlarmDetailContextInput): Partial<AiPageContext> {
  if (!input.visible) return { sections: [], images: [] };
  const form = input.formData || {};
  const labels = input.labels;
  const identity = [
    '正在查看告警详情',
    form.alert_id ? `告警 id: ${form.alert_id}` : form.id != null ? `告警 id: ${form.id}` : '',
    form.title ? `名称: ${form.title}` : '',
    form.content ? `内容: ${form.content}` : '',
    `级别: ${labels.level(form.level)}`,
    `状态: ${labels.state(form.status)}`,
    form.duration ? `持续: ${form.duration}` : '',
    form.first_event_time ? `首次事件: ${labels.formatTime(form.first_event_time)}` : '',
    form.last_event_time ? `最近事件: ${labels.formatTime(form.last_event_time)}` : '',
    form.incident_name ? `所属事故: ${form.incident_name}` : '',
    input.pageLoading ? '详情加载中' : '',
  ].filter(Boolean);

  const objects = labels.objects(form);
  const fieldLines = [
    form.operator_user ? `操作人: ${form.operator_user}` : '',
    form.notify_status != null && form.notify_status !== ''
      ? `通知: ${labels.notifyStatus(form.notify_status)}`
      : '',
    objects ? `对象: ${objects}` : form.resource_name ? `对象: ${form.resource_name}` : '',
    form.resource_type && !form.monitor_objects?.length ? `对象类型: ${form.resource_type}` : '',
  ].filter(Boolean);

  const allEvents = [...(input.eventData || [])].sort((left, right) => eventTimeValue(right) - eventTimeValue(left));
  const attached = allEvents.slice(0, ALARM_DETAIL_EVENT_LIMIT);
  const total = input.eventTotal ?? allEvents.length;
  const eventLines = input.eventLoading
    ? ['事件加载中']
    : allEvents.length
      ? [
        `共 ${total} 条，已附最近 ${attached.length} 条`,
        ...attached.map((item) => cleanLabel([
          labels.formatTime(item.received_at || item.start_time),
          labels.level(item.level),
          item.title || item.description || '',
          item.resource_name || '',
          item.action || '',
        ].filter(Boolean).join(' '))),
      ]
      : ['暂无事件'];

  const sections: AiContextSection[] = [
    { id: 'alarm-center-detail-identity', label: '当前告警详情', content: identity.join('\n'), priority: 10 },
    ...(fieldLines.length
      ? [{ id: 'alarm-center-detail-fields', label: '详情字段', content: fieldLines.join('\n'), priority: 9 }]
      : []),
    { id: 'alarm-center-detail-events', label: '事件', content: eventLines.join('\n'), priority: 8 },
  ];
  return { app: 'alarm', sections, images: [] };
}
