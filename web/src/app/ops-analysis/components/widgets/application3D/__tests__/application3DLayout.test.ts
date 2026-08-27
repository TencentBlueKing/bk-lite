import { describe, expect, it } from 'vitest';
import {
  APPLICATION3D_CAMERA_FOV,
  buildApplication3DLayout,
  fitApplication3DCameraDistance,
  formatApplication3DCardTitle,
  formatApplicationAlarmBadge,
  resolveApplication3DBadge,
  resolveApplication3DCardVisual,
  shouldShowApplication3DAlertBadge,
  UNKNOWN_STATUS_BADGE,
} from '../application3DLayout';
import {
  badgeRect,
  CARD_BADGE,
  CARD_GLASS,
  CARD_TONE,
  ellipsizeText,
  paintApplication3DCard,
  paintApplication3DCardSide,
} from '../application3DCardStyle';

describe('application3D layout', () => {
  it('uses a continuous aspect-aware wall', () => {
    const wide = buildApplication3DLayout(20, 2);
    const tall = buildApplication3DLayout(20, 0.6);
    expect(wide.columns).toBeGreaterThan(tall.columns);
    expect(wide.columns * wide.rows).toBeGreaterThanOrEqual(20);
  });

  it('selects a balanced centered composition instead of a sparse final row', () => {
    const layout = buildApplication3DLayout(16, 1.84);
    expect(layout.columns).toBe(6);
    expect(layout.rowCardCounts).toEqual([6, 6, 4]);
    expect(layout.rowCardCounts.at(-1)).toBeGreaterThanOrEqual(layout.columns / 2);
  });

  it('reduces card size for dense walls without dropping cards', () => {
    const few = buildApplication3DLayout(6, 1.6);
    const regular = buildApplication3DLayout(20, 1.6);
    const dense = buildApplication3DLayout(200, 1.6);
    expect(regular.cardWidth).toBeLessThan(few.cardWidth);
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
    expect(normal.statusLabel).toBe('无活跃告警');
    expect(normal.cardTone).toBe('normal');
    expect(normal.showBadge).toBe(false);
    expect(normal.badgeText).toBe('');

    const critical = resolveApplication3DCardVisual({
      name: '本地演示-运营门户',
      health: {
        state: 'alarming',
        reason: 'active_alarm',
        activeAlarmCount: 2,
        highestSeverity: { id: 'critical', label: '严重', color: 'critical' },
      },
    });
    expect(critical.statusLabel).toBe('严重告警');
    expect(critical.cardTone).toBe('critical');
    expect(critical.badgeText).toBe('2');
    expect(critical.showBadge).toBe(true);
    expect(critical.neonLevel).toBe('fatal');

    const warning = resolveApplication3DCardVisual({
      name: '本地演示-采购管理',
      health: {
        state: 'alarming',
        reason: 'active_alarm',
        activeAlarmCount: 3,
        highestSeverity: { id: 'warning', label: '警告', color: 'warning' },
      },
    });
    expect(warning.statusLabel).toBe('警告');
    expect(warning.cardTone).toBe('warning');
    expect(warning.showBadge).toBe(true);
    expect(warning.badgeText).toBe('3');

    const error = resolveApplication3DCardVisual({
      name: '本地演示-订单服务',
      health: {
        state: 'alarming',
        reason: 'active_alarm',
        activeAlarmCount: 4,
        highestSeverity: { id: 'error', label: '错误', color: 'danger' },
      },
    });
    expect(error.statusLabel).toBe('错误告警');
    expect(error.cardTone).toBe('error');
    expect(error.showBadge).toBe(true);
    expect(error.badgeText).toBe('4');
    expect(error.statusLabel).not.toBe('状态未知');

    const noData = resolveApplication3DCardVisual({
      name: '本地演示-消息中间件',
      health: {
        state: 'alarming',
        reason: 'active_alarm',
        activeAlarmCount: 1,
        highestSeverity: { id: 'critical', label: '严重', color: 'critical' },
      },
    });
    expect(noData.statusLabel).toBe('严重告警');
    expect(noData.cardTone).toBe('critical');
    expect(noData.neonLevel).toBe('fatal');
    expect(noData.showBadge).toBe(true);
    expect(noData.badgeText).toBe('1');
    expect(noData.statusLabel).not.toBe('状态未知');

    const info = resolveApplication3DCardVisual({
      name: '本地演示-配置中心',
      health: {
        state: 'alarming',
        reason: 'active_alarm',
        activeAlarmCount: 2,
        highestSeverity: { id: 'info', label: '提示', color: 'info' },
      },
    });
    expect(info.cardTone).toBe('info');
    expect(info.statusLabel).toBe('提示');
    expect(info.statusLabel).not.toBe('状态未知');
    expect(info.showBadge).toBe(true);
    expect(info.badgeText).toBe('2');

    const emptyLevelAlarming = resolveApplication3DCardVisual({
      name: '本地演示-空级别无数据',
      health: {
        state: 'alarming',
        reason: 'active_alarm',
        activeAlarmCount: 1,
        highestSeverity: { id: 'warning', label: '警告', color: 'warning' },
      },
    });
    expect(emptyLevelAlarming.statusLabel).toBe('警告');
    expect(emptyLevelAlarming.statusLabel).not.toBe('严重告警');
    expect(emptyLevelAlarming.statusLabel).not.toBe('状态未知');
    expect(emptyLevelAlarming.cardTone).toBe('warning');
    expect(emptyLevelAlarming.neonLevel).toBe('warning');
    expect(emptyLevelAlarming.showBadge).toBe(true);
    expect(emptyLevelAlarming.badgeText).toBe('1');

    const unmappedLevelFallback = resolveApplication3DCardVisual({
      name: '本地演示-未映射级别',
      health: {
        state: 'alarming',
        reason: 'active_alarm',
        activeAlarmCount: 1,
        highestSeverity: null,
      },
    });
    expect(unmappedLevelFallback.statusLabel).toBe('警告');
    expect(unmappedLevelFallback.cardTone).toBe('warning');
    expect(unmappedLevelFallback.neonLevel).toBe('warning');
    expect(unmappedLevelFallback.statusLabel).not.toBe('严重告警');

    const unavailable = resolveApplication3DCardVisual({
      name: '本地演示-财务任务调度',
      health: {
        state: 'unknown',
        reason: 'unavailable',
        activeAlarmCount: null,
        highestSeverity: null,
      },
    });
    expect(unavailable.statusLabel).toBe('状态未知');
    expect(unavailable.cardTone).toBe('unknown');
    expect(unavailable.showBadge).toBe(true);
    expect(unavailable.badgeText).toBe(UNKNOWN_STATUS_BADGE);

    const english = resolveApplication3DCardVisual(
      {
        name: 'ops-portal',
        health: {
          state: 'alarming',
          reason: 'active_alarm',
          activeAlarmCount: 1,
          highestSeverity: { id: 'critical', label: '严重', color: 'critical' },
        },
      },
      (id, fallback) => {
        const map: Record<string, string> = {
          'dashboard.application3DStatus_critical': 'Critical alarm',
        };
        return map[id] ?? fallback ?? id;
      },
    );
    expect(english.statusLabel).toBe('Critical alarm');
  });

  it('uses a wider portrait card without becoming landscape', () => {
    const layout = buildApplication3DLayout(12, 1.6);
    const ratio = layout.cardWidth / layout.cardHeight;
    expect(ratio).toBeGreaterThanOrEqual(0.78);
    expect(ratio).toBeLessThanOrEqual(0.82);
    expect(layout.gapX / layout.cardWidth).toBeCloseTo(0.4 / 3.2, 5);
  });

  it('frames a 16-card wall closer than the legacy pad without filling the viewport', () => {
    const viewportAspect = 1.84;
    const layout = buildApplication3DLayout(16, viewportAspect);
    expect(layout.columns * layout.rows).toBeGreaterThanOrEqual(16);
    const next = fitApplication3DCameraDistance(
      layout.wallWidth,
      layout.wallHeight,
      viewportAspect,
    );
    const halfFov = ((APPLICATION3D_CAMERA_FOV * Math.PI) / 180) / 2;
    const tan = Math.tan(halfFov);
    const tight = Math.max(
      layout.wallHeight / (2 * tan),
      layout.wallWidth / (2 * tan * viewportAspect),
    );
    const legacy = Math.max(tight, 40 * 0.55) + 2;
    expect(next).toBeLessThan(legacy * 0.8);
    expect(next).toBeGreaterThan(tight);
    const widthFill = tight > 0 ? (layout.wallWidth / (2 * tan * viewportAspect)) / next : 0;
    const heightFill = (layout.wallHeight / (2 * tan)) / next;
    expect(widthFill).toBeGreaterThan(0.6);
    expect(widthFill).toBeLessThan(0.8);
    expect(heightFill).toBeGreaterThan(0.48);
    expect(heightFill).toBeLessThan(0.78);
  });

  it('keeps title larger than status after the readability bump', () => {
    expect(CARD_GLASS.titleSize).toBeGreaterThanOrEqual(53);
    expect(CARD_GLASS.statusSize).toBeGreaterThanOrEqual(25);
    expect(CARD_GLASS.titleSize / CARD_GLASS.statusSize).toBeGreaterThan(1.9);
  });

  it('hides alarm-count badges for zero, unknown, and normal', () => {
    expect(shouldShowApplication3DAlertBadge({ state: 'normal', activeAlarmCount: 0 })).toBe(false);
    expect(shouldShowApplication3DAlertBadge({ state: 'unknown', activeAlarmCount: null })).toBe(false);
    expect(shouldShowApplication3DAlertBadge({ state: 'unknown', activeAlarmCount: 1 })).toBe(false);
    expect(shouldShowApplication3DAlertBadge({ state: 'alarming', activeAlarmCount: 4 })).toBe(true);
  });

  it('uses -- for unknown status badges instead of a fake count', () => {
    expect(resolveApplication3DBadge(
      { state: 'unknown', activeAlarmCount: 1 },
      'unknown',
    )).toEqual({ showBadge: true, badgeText: '--' });
    expect(resolveApplication3DBadge(
      { state: 'unknown', activeAlarmCount: null },
      'unknown',
    )).toEqual({ showBadge: true, badgeText: '--' });
    expect(resolveApplication3DBadge(
      { state: 'normal', activeAlarmCount: 0 },
      'normal',
    )).toEqual({ showBadge: false, badgeText: '' });
  });

  it('ellipsizes long titles without wrapping', () => {
    const measure = (value: string) => value.length * 10;
    expect(ellipsizeText('供应链数据库', 200, measure)).toBe('供应链数据库');
    const clipped = ellipsizeText('供应链数据库集群主节点', 80, measure);
    expect(clipped.endsWith('…')).toBe(true);
    expect(clipped.includes('\n')).toBe(false);
    expect(measure(clipped)).toBeLessThanOrEqual(80);
  });

  it('ranks status edges by width, opacity and glow instead of hue alone', () => {
    const edgeAlpha = (tone: keyof typeof CARD_TONE) => {
      const match = /,\s*([0-9.]+)\)$/.exec(CARD_TONE[tone].edge);
      return Number(match?.[1] ?? 0);
    };
    expect(CARD_TONE.critical.edgeWidth).toBeGreaterThan(CARD_TONE.error.edgeWidth);
    expect(CARD_TONE.error.edgeWidth).toBeGreaterThan(CARD_TONE.warning.edgeWidth);
    expect(CARD_TONE.warning.edgeWidth).toBeGreaterThan(CARD_TONE.info.edgeWidth);
    expect(CARD_TONE.info.edgeWidth).toBeGreaterThan(CARD_TONE.unknown.edgeWidth);
    expect(CARD_TONE.unknown.edgeWidth).toBeGreaterThan(CARD_TONE.normal.edgeWidth);
    expect(edgeAlpha('critical')).toBeGreaterThan(edgeAlpha('warning'));
    expect(edgeAlpha('warning')).toBeGreaterThan(edgeAlpha('unknown'));
    expect(edgeAlpha('unknown')).toBeGreaterThan(edgeAlpha('normal'));
    expect(CARD_TONE.normal.glow.width).toBe(0);
    expect(CARD_TONE.unknown.glow.width).toBe(0);
    expect(CARD_TONE.info.glow.width).toBe(0);
    expect(CARD_TONE.warning.glow.width).toBeGreaterThan(0);
    expect(CARD_TONE.critical.glow.width).toBeGreaterThan(CARD_TONE.warning.glow.width);
    expect(CARD_TONE.critical.glow.width).toBeLessThanOrEqual(28);
    expect(CARD_TONE.warning.glow.width).toBeLessThanOrEqual(16);
    expect(CARD_TONE.unknown.edge).toContain('118, 126, 136');
    expect(CARD_TONE.normal.edge).toContain('206, 220, 232');
    expect(CARD_BADGE.height).toBeGreaterThanOrEqual(44);
    expect(CARD_GLASS.bodyRim).toContain('0.28');
    expect(CARD_GLASS.frostAlpha).toBeLessThan(0.07);
    expect(CARD_GLASS.frostAlpha).toBeGreaterThan(0.02);
  });

  it('paints a rectangular unknown badge as -- and omits front chrome on the back', () => {
    const fillTexts: string[] = [];
    const ctx = {
      canvas: { width: 512, height: 640 },
      clearRect: () => undefined,
      save: () => undefined,
      restore: () => undefined,
      beginPath: () => undefined,
      moveTo: () => undefined,
      arcTo: () => undefined,
      closePath: () => undefined,
      clip: () => undefined,
      fill: () => undefined,
      stroke: () => undefined,
      fillRect: () => undefined,
      fillText: (text: string) => {
        fillTexts.push(text);
      },
      measureText: (text: string) => ({ width: text.length * 18 }),
      arc: () => undefined,
      createRadialGradient: () => ({ addColorStop: () => undefined }),
      createLinearGradient: () => ({ addColorStop: () => undefined }),
    } as unknown as CanvasRenderingContext2D;

    const visual = resolveApplication3DCardVisual({
      name: '代码质量平台',
      health: {
        state: 'unknown',
        reason: 'unavailable',
        activeAlarmCount: 1,
        highestSeverity: null,
      },
    });
    paintApplication3DCard(ctx, visual, 'code-quality', 'front');
    expect(fillTexts).toContain('代码质量平台');
    expect(fillTexts).toContain('状态未知');
    expect(fillTexts).toContain('--');
    expect(fillTexts).not.toContain('1');
    const badge = badgeRect('--', 512, 640);
    expect(badge.width).toBeGreaterThan(badge.height);
    expect(badge.radius).toBe(CARD_BADGE.radius);

    fillTexts.length = 0;
    paintApplication3DCard(ctx, visual, 'code-quality', 'back');
    expect(fillTexts).toEqual([]);
  });

  it('paints no outer glow for normal and unknown status edges', () => {
    const shadows: number[] = [];
    const makeCtx = () =>
      ({
        canvas: { width: 512, height: 640 },
        clearRect: () => undefined,
        save: () => undefined,
        restore: () => undefined,
        beginPath: () => undefined,
        moveTo: () => undefined,
        arcTo: () => undefined,
        closePath: () => undefined,
        clip: () => undefined,
        fill: () => undefined,
        stroke: () => undefined,
        fillRect: () => undefined,
        fillText: () => undefined,
        measureText: (text: string) => ({ width: text.length * 18 }),
        arc: () => undefined,
        createRadialGradient: () => ({ addColorStop: () => undefined }),
        createLinearGradient: () => ({ addColorStop: () => undefined }),
        set shadowBlur(value: number) {
          shadows.push(value);
        },
        get shadowBlur() {
          return 0;
        },
      }) as unknown as CanvasRenderingContext2D;

    const unknown = resolveApplication3DCardVisual({
      name: '代码质量平台',
      health: {
        state: 'unknown',
        reason: 'unavailable',
        activeAlarmCount: 1,
        highestSeverity: null,
      },
    });
    const normal = resolveApplication3DCardVisual({
      name: '运营门户',
      health: {
        state: 'normal',
        reason: 'no_active_alarm',
        activeAlarmCount: 0,
        highestSeverity: { id: 'normal', label: '正常', color: 'success' },
      },
    });
    paintApplication3DCard(makeCtx(), unknown, 'code-quality', 'front');
    paintApplication3DCard(makeCtx(), normal, 'ops-portal', 'front');
    expect(shadows).toEqual([]);

    const critical = resolveApplication3DCardVisual({
      name: '计费服务',
      health: {
        state: 'alarming',
        reason: 'active_alarm',
        activeAlarmCount: 2,
        highestSeverity: { id: 'critical', label: '严重', rank: 3, color: 'critical' },
      },
    });
    paintApplication3DCard(makeCtx(), critical, 'billing', 'front');
    expect(shadows).toContain(CARD_TONE.critical.glow.width);
  });

  it('paints no_data critical and info as alarming visuals, not 状态未知', () => {
    const fillTexts: string[] = [];
    const ctx = {
      canvas: { width: 512, height: 640 },
      clearRect: () => undefined,
      save: () => undefined,
      restore: () => undefined,
      beginPath: () => undefined,
      moveTo: () => undefined,
      arcTo: () => undefined,
      closePath: () => undefined,
      clip: () => undefined,
      fill: () => undefined,
      stroke: () => undefined,
      fillRect: () => undefined,
      fillText: (text: string) => {
        fillTexts.push(text);
      },
      measureText: (text: string) => ({ width: text.length * 18 }),
      arc: () => undefined,
      createRadialGradient: () => ({ addColorStop: () => undefined }),
      createLinearGradient: () => ({ addColorStop: () => undefined }),
    } as unknown as CanvasRenderingContext2D;

    const noDataCritical = resolveApplication3DCardVisual({
      name: '消息中间件',
      health: {
        state: 'alarming',
        reason: 'active_alarm',
        activeAlarmCount: 1,
        highestSeverity: { id: 'critical', label: '严重', color: 'critical' },
      },
    });
    paintApplication3DCard(ctx, noDataCritical, 'mq', 'front');
    expect(fillTexts).toContain('严重告警');
    expect(fillTexts).toContain('1');
    expect(fillTexts).not.toContain('状态未知');
    expect(fillTexts).not.toContain('--');

    fillTexts.length = 0;
    const info = resolveApplication3DCardVisual({
      name: '配置中心',
      health: {
        state: 'alarming',
        reason: 'active_alarm',
        activeAlarmCount: 1,
        highestSeverity: { id: 'info', label: '提示', color: 'info' },
      },
    });
    paintApplication3DCard(ctx, info, 'config', 'front');
    expect(fillTexts).toContain('提示');
    expect(fillTexts).toContain('1');
    expect(fillTexts).not.toContain('状态未知');
    expect(fillTexts).not.toContain('--');
  });

  it('paints card sides as translucent glass with rim light, not a solid slab', () => {
    const gradients: number[] = [];
    const ctx = {
      canvas: { width: 48, height: 256 },
      clearRect: () => undefined,
      fillRect: () => undefined,
      createLinearGradient: (x0: number, y0: number, x1: number, y1: number) => {
        gradients.push(x1 - x0, y1 - y0);
        return { addColorStop: () => undefined };
      },
    } as unknown as CanvasRenderingContext2D;
    paintApplication3DCardSide(ctx, 'normal');
    expect(gradients).toEqual([48, 0, 0, 256]);
  });
});
