import type { AiContextSection, AiPageContext } from '@/components/ai-page-context/types';

export const INCIDENT_DETAIL_ALERT_LIMIT = 30;

export interface IncidentDetailContextLabels {
  level: (value?: string | number) => string;
  state: (value?: string) => string;
  formatTime: (value?: string) => string;
  team: (value?: unknown) => string;
}

export interface IncidentDetailContextInput {
  visible: boolean;
  pageLoading?: boolean;
  alertLoading?: boolean;
  incident?: Record<string, any>;
  alerts?: Array<Record<string, any>>;
  labels: IncidentDetailContextLabels;
}

const cleanLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

const alertTimeValue = (item: Record<string, any>): number => {
  const raw = item.last_event_time || item.first_event_time || item.updated_at;
  const ts = raw ? Date.parse(String(raw)) : Number.NaN;
  return Number.isFinite(ts) ? ts : 0;
};

export function buildIncidentDetailPageContext(
  input: IncidentDetailContextInput,
): Partial<AiPageContext> {
  if (!input.visible) return { sections: [], images: [] };
  const incident = input.incident || {};
  const labels = input.labels;
  const identity = [
    '正在查看事故详情',
    incident.incident_id ? `事故 id: ${incident.incident_id}` : '',
    incident.id != null ? `记录 id: ${incident.id}` : '',
    incident.title ? `名称: ${incident.title}` : '',
    incident.level != null && incident.level !== '' ? `级别: ${labels.level(incident.level)}` : '',
    incident.status ? `状态: ${labels.state(incident.status)}` : '',
    input.pageLoading ? '详情加载中' : '',
  ].filter(Boolean);

  const fieldLines = [
    incident.created_at ? `创建时间: ${labels.formatTime(incident.created_at)}` : '',
    incident.sources ? `来源: ${incident.sources}` : '',
    incident.operator_users ? `负责人: ${incident.operator_users}` : '',
    labels.team(incident.team) ? `团队: ${labels.team(incident.team)}` : '',
    incident.note ? `备注: ${incident.note}` : '',
    incident.alert_count != null ? `告警数: ${incident.alert_count}` : '',
  ].filter(Boolean);

  const allAlerts = [...(input.alerts || [])].sort((left, right) => alertTimeValue(right) - alertTimeValue(left));
  const attached = allAlerts.slice(0, INCIDENT_DETAIL_ALERT_LIMIT);
  const alertLines = input.alertLoading
    ? ['关联告警加载中']
    : allAlerts.length
      ? [
        `共 ${allAlerts.length} 条，已附 ${attached.length} 条`,
        ...attached.map((item) => cleanLabel([
          labels.level(item.level),
          item.title || item.content || '',
          labels.state(item.status),
          item.resource_name || '',
        ].filter(Boolean).join(' '))),
      ]
      : ['暂无关联告警'];

  const sections: AiContextSection[] = [
    { id: 'incident-detail-identity', label: '当前事故详情', content: identity.join('\n'), priority: 10 },
    ...(fieldLines.length
      ? [{ id: 'incident-detail-fields', label: '详情字段', content: fieldLines.join('\n'), priority: 9 }]
      : []),
    { id: 'incident-detail-alerts', label: '关联告警', content: alertLines.join('\n'), priority: 8 },
  ];
  return { app: 'alarm', sections, images: [] };
}
