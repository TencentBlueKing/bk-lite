import { describe, expect, it } from 'vitest';

import { ALERT_DETAIL_EVENT_LIMIT, buildAlertDetailPageContext } from '../alertDetail.context';

const labels = {
  level: (value?: string) => ({ critical: '严重', warning: '警告' }[value || ''] || value || '--'),
  state: (value?: string) => ({ new: '活跃', closed: '关闭' }[value || ''] || value || '--'),
  alertType: (value?: string) => ({ alert: '阈值' }[value || ''] || value || '--'),
  action: (value?: string) => ({ triggered: '触发', recovered: '恢复' }[value || ''] || value || ''),
  formatTime: (value?: string) => value || '--',
  formatValue: (_metric: unknown, value: unknown) => String(value ?? ''),
  notice: (noticed?: boolean) => (noticed ? '已通知' : '未通知'),
  formatPerson: (value?: unknown) => (value == null || value === '' ? '' : `用户${value}`),
  formatUnit: (unitId?: string) => (unitId === 'percent' ? '%' : unitId || ''),
};

describe('alertDetail.context', () => {
  it('returns no sections when the drawer is closed', () => {
    const snapshot = buildAlertDetailPageContext({
      visible: false,
      formData: { id: 1, content: 'CPU 高' },
      eventData: [{ id: 'ev-1' }],
      labels,
    });
    expect(snapshot.sections || []).toEqual([]);
  });

  it('includes identity, fields, and events while still on the information tab', () => {
    const snapshot = buildAlertDetailPageContext({
      visible: true,
      formData: {
        id: 9,
        content: 'CPU 超阈值',
        level: 'critical',
        status: 'new',
        alert_type: 'alert',
        updated_at: '2026-01-01 12:00:00',
        monitor_instance_name: 'host-a',
        policy: { name: 'CPU 策略' },
        metric: { display_name: 'CPU 使用率', dimensions: [{ name: 'host', description: '主机' }] },
        dimensions: { host: 'host-a' },
      },
      eventData: [
        { id: 'ev-1', event_time: '2026-01-01 12:00:00', action: 'triggered', level: 'critical', content: 'CPU 超阈值', value: 95 },
      ],
      labels,
    });
    const text = (snapshot.sections || []).map((section) => `${section.id}\n${section.content}`).join('\n');
    expect(text).toContain('alert-detail-identity');
    expect(text).toContain('CPU 超阈值');
    expect(text).toContain('host-a');
    expect(text).toContain('CPU 策略');
    expect(text).toContain('触发');
    expect(text).toContain('95');
    expect(snapshot.sections?.find((section) => section.id === 'alert-detail-events')?.priority).toBe(8);
  });

  it('keeps the newest 30 events and writes the total', () => {
    const eventData = Array.from({ length: 35 }, (_, index) => ({
      id: `ev-${index}`,
      event_time: `2026-01-01T12:${String(index).padStart(2, '0')}:00Z`,
      action: 'triggered',
      level: 'critical',
      content: `event-${index}`,
      value: index,
    }));
    const snapshot = buildAlertDetailPageContext({
      visible: true,
      formData: { id: 1, content: 'CPU 高' },
      eventData,
      labels,
    });
    const eventSection = snapshot.sections?.find((section) => section.id === 'alert-detail-events')?.content || '';
    expect(eventSection).toContain('共 35 条');
    expect(eventSection).toContain(`已附最近 ${ALERT_DETAIL_EVENT_LIMIT} 条`);
    expect(eventSection).toContain('event-34');
    expect(eventSection).toContain('event-5');
    expect(eventSection).not.toMatch(/(^|\n)[^\n]*\bevent-4\b/);
    expect(eventSection).not.toMatch(/(^|\n)[^\n]*\bevent-0\b/);
  });

  it('includes notice, notifiers, operator, end time, and metric unit', () => {
    const snapshot = buildAlertDetailPageContext({
      visible: true,
      formData: {
        id: 3,
        content: '磁盘满',
        status: 'closed',
        operator: 'alice',
        end_event_time: '2026-01-02 08:00:00',
        notice_users_display: ['bob', 'carol'],
        policy: { name: '磁盘策略', notice: true },
        metric: { display_name: '磁盘使用率' },
      },
      chartUnit: 'percent',
      labels,
    });
    const fields = snapshot.sections?.find((section) => section.id === 'alert-detail-fields')?.content || '';
    expect(fields).toContain('通知: 已通知');
    expect(fields).toContain('通知人: bob,carol');
    expect(fields).toContain('操作人: 用户alice');
    expect(fields).toContain('结束时间: 2026-01-02 08:00:00');
    expect(fields).toContain('指标: 磁盘使用率（%）');
  });

  it('says events are loading instead of treating empty as zero', () => {
    const snapshot = buildAlertDetailPageContext({
      visible: true,
      pageLoading: false,
      eventLoading: true,
      formData: { id: 1, content: 'CPU 高' },
      eventData: [],
      labels,
    });
    const text = (snapshot.sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('事件加载中');
    expect(text).not.toContain('共 0 条');
  });
});
