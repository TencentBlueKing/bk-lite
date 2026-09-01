import { describe, expect, it } from 'vitest';
import {
  buildTrendYTicks,
  formatAlarmDurationSeconds,
  formatAlarmOccurredAt,
  groupDetailProperties,
  projectTrendX,
  resolveDetailStatus,
} from '../application3DDetailChrome';

describe('application3D detail chrome helpers', () => {
  it('formats duration and empty occurredAt', () => {
    expect(formatAlarmDurationSeconds(60)).toBe('1m 0s');
    expect(formatAlarmDurationSeconds(3661)).toBe('1h 1m');
    expect(formatAlarmOccurredAt(null)).toBe('-');
    expect(formatAlarmOccurredAt('not-a-date')).toBe('-');
  });

  it('strips trailing alarm count from detail status label', () => {
    const status = resolveDetailStatus(
      {
        name: 'demo',
        health: {
          state: 'alarming',
          reason: 'alarm',
          activeAlarmCount: 2,
          highestSeverity: { id: 'warning', label: '警告', color: 'warning' },
        },
      },
      (key, fallback) => (key.endsWith('_warning') ? '警告' : (fallback ?? key)),
    );
    expect(status.statusLabel).toBe('警告');
    expect(status.statusLabel).not.toMatch(/\d/);
  });

  it('builds y ticks spanning thresholds', () => {
    const ticks = buildTrendYTicks(40, 120);
    expect(ticks[0]).toBeLessThanOrEqual(40);
    expect(ticks[ticks.length - 1]).toBeGreaterThanOrEqual(120);
  });

  it('groups system identity properties into existing sections, not other', () => {
    const sections = groupDetailProperties([
      { key: 'system_code', label: '系统编码', displayValue: 'SYS-1' },
      { key: 'status', label: '状态', displayValue: '运行中' },
      { key: 'organization', label: '组织', displayValue: '运营' },
      { key: 'app_id', label: '应用ID', displayValue: 'app-1' },
      { key: 'app_type', label: '应用类型', displayValue: 'web' },
      { key: 'operator', label: '负责人', displayValue: 'alice' },
      { key: 'bak_operator', label: '备份负责人', displayValue: 'bob' },
      { key: 'productor', label: '产品', displayValue: 'carol' },
      { key: 'developer', label: '开发', displayValue: 'dave' },
      { key: 'tester', label: '测试', displayValue: 'erin' },
      { key: 'comment', label: '描述', displayValue: '系统备注' },
    ]);

    expect(sections.basic.map((item) => item.key)).toEqual([
      'system_code',
      'status',
      'organization',
      'app_id',
      'app_type',
    ]);
    expect(sections.maintain.map((item) => item.key)).toEqual([
      'operator',
      'bak_operator',
      'productor',
      'developer',
      'tester',
    ]);
    expect(sections.description.map((item) => item.key)).toEqual(['comment']);
    expect(sections.other).toEqual([]);
  });

  it('projects marker x by timestamp domain', () => {
    const early = projectTrendX(0, 0, 100, 36, 200);
    const mid = projectTrendX(50, 0, 100, 36, 200);
    const late = projectTrendX(100, 0, 100, 36, 200);
    expect(early).toBe(36);
    expect(mid).toBe(136);
    expect(late).toBe(236);
  });
});
