import { describe, expect, it } from 'vitest';
import {
  buildApplication3DLayout,
  formatApplication3DCardTitle,
  formatApplicationAlarmBadge,
  resolveApplication3DCardVisual,
} from '../application3DLayout';

describe('application3D layout', () => {
  it('uses a continuous aspect-aware wall', () => {
    const wide = buildApplication3DLayout(20, 2);
    const tall = buildApplication3DLayout(20, 0.6);
    expect(wide.columns).toBeGreaterThan(tall.columns);
    expect(wide.columns * wide.rows).toBeGreaterThanOrEqual(20);
  });

  it('reduces card size for dense walls without dropping cards', () => {
    const regular = buildApplication3DLayout(20, 1.6);
    const dense = buildApplication3DLayout(200, 1.6);
    expect(dense.cardWidth).toBeLessThan(regular.cardWidth);
    expect(dense.columns * dense.rows).toBeGreaterThanOrEqual(200);
  });

  it('formats exact and overflow alarm badges', () => {
    expect(formatApplicationAlarmBadge(null)).toBe('?');
    expect(formatApplicationAlarmBadge(0)).toBe('0');
    expect(formatApplicationAlarmBadge(99)).toBe('99');
    expect(formatApplicationAlarmBadge(100)).toBe('99+');
  });

  it('strips demo name prefix for wall titles', () => {
    expect(formatApplication3DCardTitle('本地演示-运营门户')).toBe('运营门户');
    expect(formatApplication3DCardTitle('运营门户')).toBe('运营门户');
  });

  it('differentiates health reasons and severities on wall cards', () => {
    const normal = resolveApplication3DCardVisual({
      name: '本地演示-供应链数据库',
      health: {
        state: 'normal',
        reason: 'no_active_alarm',
        activeAlarmCount: 0,
        highestSeverity: { id: 'normal', label: '正常', color: 'success' },
      },
    });
    expect(normal.statusLabel).toBe('NORMAL');
    expect(normal.showBadge).toBe(false);

    const critical = resolveApplication3DCardVisual({
      name: '本地演示-运营门户',
      health: {
        state: 'alarming',
        reason: 'active_alarm',
        activeAlarmCount: 2,
        highestSeverity: { id: 'critical', label: '致命', color: 'critical' },
      },
    });
    expect(critical.statusLabel).toBe('致命');
    expect(critical.badgeText).toBe('2');
    expect(critical.accentTokenCandidates).toContain('--color-fail');

    const noData = resolveApplication3DCardVisual({
      name: '本地演示-消息中间件',
      health: {
        state: 'unknown',
        reason: 'no_data_alarm',
        activeAlarmCount: 1,
        highestSeverity: null,
      },
    });
    expect(noData.statusLabel).toBe('NO DATA');
    expect(noData.accentTokenCandidates).toContain('--theme-color-status-warning');

    const unavailable = resolveApplication3DCardVisual({
      name: '本地演示-财务任务调度',
      health: {
        state: 'unknown',
        reason: 'unavailable',
        activeAlarmCount: null,
        highestSeverity: null,
      },
    });
    expect(unavailable.statusLabel).toBe('UNAVAILABLE');
    expect(unavailable.badgeText).toBe('?');
  });
});
