import { describe, expect, it } from 'vitest';

import { ALARM_DETAIL_EVENT_LIMIT, buildAlarmDetailPageContext } from '../alarmDetail.context';

const labels = {
  level: (value?: string | number) => ({ '1': '致命', '2': '预警' }[String(value || '')] || String(value || '--')),
  state: (value?: string) => ({ pending: '待响应', processing: '处理中' }[value || ''] || value || '--'),
  formatTime: (value?: string) => value || '--',
  notifyStatus: (value?: string) => value || '--',
  objects: (form: Record<string, any>) =>
    Array.isArray(form.monitor_objects)
      ? form.monitor_objects.map((item: any) => `${item.resource_type}: ${item.resource_name}`).join('；')
      : '',
};

describe('alarmDetail.context', () => {
  it('returns no sections when the drawer is closed', () => {
    const snapshot = buildAlarmDetailPageContext({
      visible: false,
      formData: { id: 1, title: 'CPU 高' },
      eventData: [{ id: 'ev-1' }],
      labels,
    });
    expect(snapshot.sections || []).toEqual([]);
  });

  it('includes identity, fields, and events while still on the information tab', () => {
    const snapshot = buildAlarmDetailPageContext({
      visible: true,
      formData: {
        id: 9,
        alert_id: 'ALT-9',
        title: 'FailedScheduling',
        content: '0/1 nodes are available',
        level: '2',
        status: 'pending',
        duration: '5m',
        first_event_time: '2026-09-10 15:28:20',
        last_event_time: '2026-09-10 15:28:20',
        operator_user: 'admin',
        notify_status: 'success',
        monitor_objects: [{ resource_type: 'Pod', resource_name: 'kube-scheduler' }],
      },
      eventData: [
        {
          id: 'ev-1',
          received_at: '2026-09-10 15:28:20',
          level: '2',
          title: 'FailedScheduling',
          resource_name: 'kube-scheduler',
        },
      ],
      labels,
    });
    const text = (snapshot.sections || []).map((section) => `${section.id}\n${section.content}`).join('\n');
    expect(text).toContain('alarm-center-detail-identity');
    expect(text).toContain('FailedScheduling');
    expect(text).toContain('ALT-9');
    expect(text).toContain('Pod: kube-scheduler');
    expect(text).toContain('admin');
    expect(snapshot.sections?.find((section) => section.id === 'alarm-center-detail-events')?.priority).toBe(8);
  });

  it('keeps the newest 30 events and writes the total', () => {
    const eventData = Array.from({ length: 35 }, (_, index) => ({
      id: `ev-${index}`,
      received_at: `2026-01-01T12:${String(index).padStart(2, '0')}:00Z`,
      title: `event-${index}`,
      level: '2',
    }));
    const snapshot = buildAlarmDetailPageContext({
      visible: true,
      formData: { id: 1, title: 'CPU 高' },
      eventData,
      eventTotal: 35,
      labels,
    });
    const eventSection = snapshot.sections?.find((section) => section.id === 'alarm-center-detail-events')?.content || '';
    expect(eventSection).toContain('共 35 条');
    expect(eventSection).toContain(`已附最近 ${ALARM_DETAIL_EVENT_LIMIT} 条`);
    expect(eventSection).toContain('event-34');
    expect(eventSection).toContain('event-5');
    expect(eventSection).not.toMatch(/(^|\n)[^\n]*\bevent-4\b/);
  });

  it('says events are loading instead of treating empty as zero', () => {
    const snapshot = buildAlarmDetailPageContext({
      visible: true,
      eventLoading: true,
      formData: { id: 1, title: 'CPU 高' },
      eventData: [],
      labels,
    });
    const text = (snapshot.sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('事件加载中');
    expect(text).not.toContain('共 0 条');
  });
});
