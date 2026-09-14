import { describe, expect, it } from 'vitest';

import {
  INCIDENT_DETAIL_ALERT_LIMIT,
  buildIncidentDetailPageContext,
} from '../incidentDetail.context';

const labels = {
  level: (value?: string | number) => ({ '1': '致命', '2': '预警' }[String(value || '')] || String(value || '--')),
  state: (value?: string) => ({ pending: '待响应', processing: '处理中' }[value || ''] || value || '--'),
  formatTime: (value?: string) => value || '--',
  team: (value?: unknown) => (Array.isArray(value) ? value.join(',') : String(value || '')),
};

describe('incidentDetail.context', () => {
  it('returns no sections when the page is not showing a detail', () => {
    const snapshot = buildIncidentDetailPageContext({
      visible: false,
      incident: { id: 1, title: '节点不可用' },
      labels,
    });
    expect(snapshot.sections || []).toEqual([]);
  });

  it('includes identity, fields, and related alerts', () => {
    const snapshot = buildIncidentDetailPageContext({
      visible: true,
      incident: {
        id: 8,
        incident_id: 'INC-8',
        title: '节点不可用',
        level: '1',
        status: 'pending',
        created_at: '2026-09-10 15:00:00',
        sources: 'K8s',
        operator_users: 'admin',
        team: ['SRE'],
        note: '正在扩容',
        alert_count: 4,
      },
      alerts: [
        { title: 'FailedScheduling', level: '2', status: 'pending', resource_name: 'node-a' },
      ],
      labels,
    });
    const text = (snapshot.sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('INC-8');
    expect(text).toContain('节点不可用');
    expect(text).toContain('K8s');
    expect(text).toContain('FailedScheduling');
    expect(text).toContain('共 1 条');
  });

  it('keeps at most 30 related alerts and writes the total', () => {
    const alerts = Array.from({ length: 35 }, (_, index) => ({
      title: `alert-${index}`,
      last_event_time: `2026-01-01T12:${String(index).padStart(2, '0')}:00Z`,
      level: '2',
      status: 'pending',
    }));
    const snapshot = buildIncidentDetailPageContext({
      visible: true,
      incident: { id: 1, title: '事故' },
      alerts,
      labels,
    });
    const section = snapshot.sections?.find((item) => item.id === 'incident-detail-alerts')?.content || '';
    expect(section).toContain('共 35 条');
    expect(section).toContain(`已附 ${INCIDENT_DETAIL_ALERT_LIMIT} 条`);
    expect(section).toContain('alert-34');
    expect(section).not.toMatch(/(^|\n)[^\n]*\balert-4\b/);
  });

  it('says related alerts are loading instead of treating empty as zero', () => {
    const snapshot = buildIncidentDetailPageContext({
      visible: true,
      pageLoading: false,
      alertLoading: true,
      incident: { id: 1, title: '事故' },
      alerts: [],
      labels,
    });
    const text = (snapshot.sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('关联告警加载中');
    expect(text).not.toContain('共 0 条');
  });
});
