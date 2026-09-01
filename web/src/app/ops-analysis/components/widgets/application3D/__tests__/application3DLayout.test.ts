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
  WALL_VIEW_COVERAGE,
} from '../application3DLayout';
import {
  CARD_GAP,
  CARD_WORLD_HEIGHT,
  CARD_WORLD_WIDTH,
} from '../application3DVisual';
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
  it('picks columns from the card count instead of a 16-card cap', () => {
    const wide = buildApplication3DLayout(16, 2);
    const tall = buildApplication3DLayout(16, 0.6);
    expect(wide.columns * wide.rows).toBeGreaterThanOrEqual(16);
    expect(tall.columns * tall.rows).toBeGreaterThanOrEqual(16);
    const denseWide = buildApplication3DLayout(20, 2);
    const denseTall = buildApplication3DLayout(20, 0.6);
    expect(denseWide.columns * denseWide.rows).toBeGreaterThanOrEqual(20);
    expect(denseTall.columns * denseTall.rows).toBeGreaterThanOrEqual(20);
    expect(denseWide.columns).toBeGreaterThan(4);
  });

  it('keeps mid-size landscape walls close to square or slightly wide, not a 2-column tower', () => {
    for (const count of [20, 22, 26]) {
      const layout = buildApplication3DLayout(count, 1.78);
      expect(layout.columns).toBeGreaterThanOrEqual(4);
      expect(layout.columns).toBeGreaterThanOrEqual(layout.rows - 1);
      expect(layout.columns / layout.rows).toBeGreaterThanOrEqual(0.7);
      expect(layout.columns / layout.rows).toBeLessThanOrEqual(2);
    }
  });

  it('lets a wide 16-card wall stay 4×4 when that matches the viewport', () => {
    const layout = buildApplication3DLayout(16, 1.84);
    expect(layout.columns).toBe(4);
    expect(layout.rows).toBe(4);
    expect(layout.rowCardCounts).toEqual([4, 4, 4, 4]);
  });

  it('keeps 8 cards on even rows instead of a 3-3-2 hole', () => {
    const layout = buildApplication3DLayout(8, 1.84);
    expect(layout.columns * layout.rows).toBe(8);
    expect(layout.rowCardCounts.every((count) => count === layout.columns)).toBe(true);
    expect(layout.columns).toBe(4);
    expect(layout.rows).toBe(2);
  });

  it('prefers a fuller last row over a single leftover card', () => {
    const layout = buildApplication3DLayout(7, 1.84);
    const last = layout.rowCardCounts[layout.rowCardCounts.length - 1];
    expect(last).toBeGreaterThan(1);
    expect(last).toBeLessThanOrEqual(layout.columns);
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

  it('keeps demo name prefix on wall titles', () => {
    expect(formatApplication3DCardTitle('本地演示-运营门户')).toBe('本地演示-运营门户');
    expect(formatApplication3DCardTitle('  运营门户  ')).toBe('运营门户');
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
    expect(normal.statusLabel).toBe('运行正常');
    expect(normal.cardTone).toBe('normal');
    expect(normal.showBadge).toBe(false);
    expect(normal.badgeText).toBe('0');

    const critical = resolveApplication3DCardVisual({
      name: '本地演示-运营门户',
      health: {
        state: 'alarming',
        reason: 'active_alarm',
        activeAlarmCount: 2,
        highestSeverity: { id: 'critical', label: '严重', color: 'critical' },
      },
    });
    expect(critical.statusLabel).toBe('严重告警 2');
    expect(critical.cardTone).toBe('critical');
    expect(critical.badgeText).toBe('2');
    expect(critical.showBadge).toBe(false);
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
    expect(warning.statusLabel).toBe('警告 3');
    expect(warning.cardTone).toBe('warning');
    expect(warning.showBadge).toBe(false);
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
    expect(error.statusLabel).toBe('错误 4');
    expect(error.cardTone).toBe('error');
    expect(error.showBadge).toBe(false);
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
    expect(noData.statusLabel).toBe('严重告警 1');
    expect(noData.cardTone).toBe('critical');
    expect(noData.neonLevel).toBe('fatal');
    expect(noData.showBadge).toBe(false);
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
    expect(info.statusLabel).toBe('提示 2');
    expect(info.statusLabel).not.toBe('状态未知');
    expect(info.showBadge).toBe(false);
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
    expect(emptyLevelAlarming.statusLabel).toBe('警告 1');
    expect(emptyLevelAlarming.statusLabel).not.toBe('严重告警');
    expect(emptyLevelAlarming.statusLabel).not.toBe('状态未知');
    expect(emptyLevelAlarming.cardTone).toBe('warning');
    expect(emptyLevelAlarming.neonLevel).toBe('warning');
    expect(emptyLevelAlarming.showBadge).toBe(false);
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
    expect(unmappedLevelFallback.statusLabel).toBe('警告 1');
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
    expect(unavailable.showBadge).toBe(false);
    expect(unavailable.badgeText).toBe(UNKNOWN_STATUS_BADGE);

    for (const reason of ['no_host', 'no_application'] as const) {
      const visual = resolveApplication3DCardVisual({
        name: '财务结算平台',
        health: {
          state: 'unknown',
          reason,
          activeAlarmCount: null,
          highestSeverity: null,
        },
      });
      expect(visual.statusLabel).toBe('状态未知');
      expect(visual.cardTone).toBe('unknown');
      expect(visual.neonLevel).toBe('remain');
      expect(visual.showBadge).toBe(false);
      expect(visual.badgeText).toBe(UNKNOWN_STATUS_BADGE);
    }

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
    expect(english.statusLabel).toBe('Critical alarm 1');
  });

  it('uses a landscape card matching the HUD mock', () => {
    const layout = buildApplication3DLayout(12, 1.6);
    const ratio = layout.cardWidth / layout.cardHeight;
    expect(ratio).toBeCloseTo(CARD_WORLD_WIDTH / CARD_WORLD_HEIGHT, 5);
    expect(ratio).toBeGreaterThan(1);
    expect(layout.gapX / layout.cardWidth).toBeCloseTo(CARD_GAP / CARD_WORLD_WIDTH, 5);
  });

  it('frames the actual wall so small grids stay readable', () => {
    const viewportAspect = 1.84;
    const sixteen = buildApplication3DLayout(16, viewportAspect);
    const four = buildApplication3DLayout(4, viewportAspect);
    const one = buildApplication3DLayout(1, viewportAspect);
    expect(sixteen.columns * sixteen.rows).toBeGreaterThanOrEqual(16);
    const sixteenDistance = fitApplication3DCameraDistance(
      sixteen.wallWidth,
      sixteen.wallHeight,
      viewportAspect,
    );
    const fourDistance = fitApplication3DCameraDistance(
      four.wallWidth,
      four.wallHeight,
      viewportAspect,
    );
    const oneDistance = fitApplication3DCameraDistance(
      one.wallWidth,
      one.wallHeight,
      viewportAspect,
    );
    expect(sixteenDistance).toBeGreaterThan(fourDistance);
    expect(oneDistance).toBe(fourDistance);

    const halfFov = ((APPLICATION3D_CAMERA_FOV * Math.PI) / 180) / 2;
    const tan = Math.tan(halfFov);
    const tight = Math.max(
      sixteen.wallHeight / (2 * tan),
      sixteen.wallWidth / (2 * tan * viewportAspect),
    );
    expect(sixteenDistance).toBeGreaterThan(tight);
    const widthFill = (sixteen.wallWidth / (2 * tan * viewportAspect)) / sixteenDistance;
    const heightFill = (sixteen.wallHeight / (2 * tan)) / sixteenDistance;
    expect(widthFill).toBeCloseTo(WALL_VIEW_COVERAGE, 5);
    expect(heightFill).toBeLessThan(WALL_VIEW_COVERAGE);
    expect(widthFill).toBeLessThan(1);
  });

  it('uses one world size for every card so a planar wall keeps them equal', () => {
    const layout = buildApplication3DLayout(16, 1.84);
    expect(layout.cardWidth).toBeGreaterThan(0);
    expect(layout.cardHeight).toBeGreaterThan(0);
    expect(layout.cardWidth).toBe(layout.cardHeight * (CARD_WORLD_WIDTH / CARD_WORLD_HEIGHT));
  });

  it('keeps title larger than status after the readability bump', () => {
    expect(CARD_GLASS.titleSize).toBeGreaterThanOrEqual(48);
    expect(CARD_GLASS.statusSize).toBeGreaterThanOrEqual(40);
    expect(CARD_GLASS.iconSize).toBeGreaterThanOrEqual(60);
    expect(CARD_GLASS.titleSize).toBeGreaterThan(CARD_GLASS.statusSize);
  });

  it('hides alarm-count badges for zero, unknown, and normal', () => {
    expect(shouldShowApplication3DAlertBadge({ state: 'normal', activeAlarmCount: 0 })).toBe(false);
    expect(shouldShowApplication3DAlertBadge({ state: 'unknown', activeAlarmCount: null })).toBe(false);
    expect(shouldShowApplication3DAlertBadge({ state: 'unknown', activeAlarmCount: 1 })).toBe(false);
    expect(shouldShowApplication3DAlertBadge({ state: 'alarming', activeAlarmCount: 4 })).toBe(false);
  });

  it('never paints a corner count chip', () => {
    expect(resolveApplication3DBadge(
      { state: 'unknown', activeAlarmCount: 1 },
      'unknown',
    )).toEqual({ showBadge: false, badgeText: '--' });
    expect(resolveApplication3DBadge(
      { state: 'unknown', activeAlarmCount: null },
      'unknown',
    )).toEqual({ showBadge: false, badgeText: '--' });
    expect(resolveApplication3DBadge(
      { state: 'normal', activeAlarmCount: 0 },
      'normal',
    )).toEqual({ showBadge: false, badgeText: '0' });
    expect(resolveApplication3DBadge(
      { state: 'alarming', activeAlarmCount: 3 },
      'warning',
    )).toEqual({ showBadge: false, badgeText: '3' });
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
    expect(CARD_TONE.normal.glow.width).toBeGreaterThan(0);
    expect(CARD_TONE.info.glow.width).toBeGreaterThan(0);
    expect(CARD_TONE.warning.glow.width).toBeGreaterThan(CARD_TONE.normal.glow.width);
    expect(CARD_TONE.critical.glow.width).toBeGreaterThan(CARD_TONE.warning.glow.width);
    expect(CARD_TONE.critical.glow.width).toBeLessThanOrEqual(28);
    expect(CARD_TONE.warning.glow.width).toBeLessThanOrEqual(16);
    expect(CARD_TONE.unknown.edge).toContain('118, 126, 136');
    expect(CARD_TONE.normal.edge).toContain('92, 154, 190');
    expect(CARD_GLASS.bodyCenter).toContain('16, 32, 48');
    expect(CARD_GLASS.bodyRim).toContain('8, 16, 28');
    expect(CARD_GLASS.frostAlpha).toBe(0);
  });

  it('paints unknown chrome without a corner chip', () => {
    const fillTexts: string[] = [];
    const ctx = {
      canvas: { width: 512, height: 640 },
      clearRect: () => undefined,
      save: () => undefined,
      restore: () => undefined,
      beginPath: () => undefined,
      moveTo: () => undefined,
      lineTo: () => undefined,
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
    expect(fillTexts).not.toContain('--');
    expect(fillTexts).not.toContain('1');
    const badge = badgeRect('--', 512, 640);
    expect(badge.width).toBeGreaterThan(badge.height);
    expect(badge.radius).toBe(CARD_BADGE.radius);

    fillTexts.length = 0;
    paintApplication3DCard(ctx, visual, 'code-quality', 'back');
    expect(fillTexts).toEqual([]);
  });

  it('paints wall chrome on a clear plate so CSS glass can show through', () => {
    const shadows: number[] = [];
    const fills: string[] = [];
    const makeCtx = () =>
      ({
        canvas: { width: 512, height: 640 },
        clearRect: () => undefined,
        save: () => undefined,
        restore: () => undefined,
        beginPath: () => undefined,
        moveTo: () => undefined,
        lineTo: () => undefined,
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
        set fillStyle(value: string) {
          fills.push(String(value));
        },
        get fillStyle() {
          return '';
        },
        set shadowBlur(value: number) {
          shadows.push(value);
        },
        get shadowBlur() {
          return 0;
        },
      }) as unknown as CanvasRenderingContext2D;

    const normal = resolveApplication3DCardVisual({
      name: '运营门户',
      health: {
        state: 'normal',
        reason: 'no_active_alarm',
        activeAlarmCount: 0,
        highestSeverity: { id: 'normal', label: '正常', color: 'success' },
      },
    });
    paintApplication3DCard(makeCtx(), normal, 'ops-portal', 'front');
    expect(shadows).not.toContain(CARD_TONE.normal.glow.width);
    expect(fills.some((value) => value.includes('16, 32, 48'))).toBe(false);
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
      lineTo: () => undefined,
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
    expect(fillTexts).toContain('严重告警 1');
    expect(fillTexts).not.toContain('1');
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
    expect(fillTexts).toContain('提示 1');
    expect(fillTexts).not.toContain('1');
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
