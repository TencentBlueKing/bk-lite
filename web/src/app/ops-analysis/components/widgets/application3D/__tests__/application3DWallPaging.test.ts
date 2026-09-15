import { describe, expect, it } from 'vitest';
import type { Application3DHealth, Application3DWallItem } from '@/app/ops-analysis/types/sceneWidget';
import {
  APPLICATION3D_WALL_PAGE_SIZE,
  paginateApplication3DWallItems,
  resolveApplication3DWallLayoutCount,
  sortApplication3DWallItems,
} from '../application3DWallPaging';

const health = (
  overrides: Partial<Application3DHealth> & Pick<Application3DHealth, 'state'>,
): Application3DHealth => ({
  reason: overrides.state === 'alarming' ? 'active_alarm' : overrides.state === 'unknown' ? 'unavailable' : 'no_active_alarm',
  activeAlarmCount: overrides.state === 'normal' ? 0 : overrides.state === 'unknown' ? null : 1,
  severityCounts: overrides.state === 'unknown' ? null : { critical: 0, error: 0, warning: 0, info: 0 },
  noDataAlarmCount: overrides.state === 'unknown' ? null : 0,
  highestSeverity: overrides.state === 'normal'
    ? { id: 'normal', label: '正常', rank: 0, color: 'success' }
    : null,
  stale: false,
  ...overrides,
});

const item = (
  id: string,
  name: string,
  itemHealth: Application3DHealth,
): Application3DWallItem => ({ id, name, health: itemHealth });

describe('application3D wall paging', () => {
  it('sorts alarming by severity then count, then unknown before normal', () => {
    const warningFew = item('w-1', '门户', health({
      state: 'alarming',
      activeAlarmCount: 2,
      highestSeverity: { id: 'warning', label: '警告', rank: 200, color: 'warning' },
    }));
    const criticalMany = item('c-2', '支付', health({
      state: 'alarming',
      activeAlarmCount: 8,
      highestSeverity: { id: 'critical', label: '严重', rank: 400, color: 'critical' },
    }));
    const criticalFew = item('c-1', '结算', health({
      state: 'alarming',
      activeAlarmCount: 3,
      highestSeverity: { id: 'critical', label: '严重', rank: 400, color: 'critical' },
    }));
    const unknownB = item('u-2', '未知乙', health({ state: 'unknown' }));
    const unknownA = item('u-1', '未知甲', health({ state: 'unknown' }));
    const normalZ = item('n-2', '正常乙', health({ state: 'normal' }));
    const normalA = item('n-1', '正常甲', health({ state: 'normal' }));

    const ordered = sortApplication3DWallItems([
      normalZ,
      warningFew,
      unknownB,
      criticalFew,
      normalA,
      unknownA,
      criticalMany,
    ]);

    expect(ordered.map((entry) => entry.id)).toEqual([
      'c-2',
      'c-1',
      'w-1',
      'u-1',
      'u-2',
      'n-1',
      'n-2',
    ]);
  });

  it('breaks remaining ties by name then id, and treats null alarm count as 0', () => {
    const sameNameLater = item('b', 'Billing', health({
      state: 'alarming',
      activeAlarmCount: null,
      highestSeverity: { id: 'error', label: '错误', rank: 300, color: 'danger' },
    }));
    const sameNameEarlier = item('a', 'Billing', health({
      state: 'alarming',
      activeAlarmCount: null,
      highestSeverity: { id: 'error', label: '错误', rank: 300, color: 'danger' },
    }));
    const namedEarlier = item('c', 'Alpha', health({
      state: 'alarming',
      activeAlarmCount: 0,
      highestSeverity: { id: 'error', label: '错误', rank: 300, color: 'danger' },
    }));

    const ordered = sortApplication3DWallItems([sameNameLater, namedEarlier, sameNameEarlier]);
    expect(ordered.map((entry) => entry.id)).toEqual(['c', 'a', 'b']);
  });

  it('pages 24 cards at a time and clamps past the last page', () => {
    expect(APPLICATION3D_WALL_PAGE_SIZE).toBe(24);
    const items = Array.from({ length: 50 }, (_, index) => item(
      `sys-${String(index + 1).padStart(2, '0')}`,
      `系统${String(index + 1).padStart(2, '0')}`,
      health({ state: 'normal' }),
    ));

    const first = paginateApplication3DWallItems(items, 1);
    expect(first.page).toBe(1);
    expect(first.totalPages).toBe(3);
    expect(first.totalCount).toBe(50);
    expect(first.pageItems).toHaveLength(24);
    expect(first.pageItems[0].id).toBe('sys-01');
    expect(first.pageItems[23].id).toBe('sys-24');
    expect(first.hasPrev).toBe(false);
    expect(first.hasNext).toBe(true);

    const last = paginateApplication3DWallItems(items, 3);
    expect(last.pageItems.map((entry) => entry.id)).toEqual(['sys-49', 'sys-50']);
    expect(last.hasPrev).toBe(true);
    expect(last.hasNext).toBe(false);

    const overflow = paginateApplication3DWallItems(items, 99);
    expect(overflow.page).toBe(3);
    expect(overflow.pageItems.map((entry) => entry.id)).toEqual(['sys-49', 'sys-50']);
  });

  it('hides paging chrome when there is at most one page', () => {
    const empty = paginateApplication3DWallItems([], 1);
    expect(empty.totalPages).toBe(0);
    expect(empty.pageItems).toEqual([]);
    expect(empty.hasPrev).toBe(false);
    expect(empty.hasNext).toBe(false);

    const single = paginateApplication3DWallItems(
      [item('only', '唯一', health({ state: 'normal' }))],
      1,
    );
    expect(single.totalPages).toBe(1);
    expect(single.hasPrev).toBe(false);
    expect(single.hasNext).toBe(false);
  });

  it('locks the 24-card layout frame while the wall is paginated', () => {
    expect(resolveApplication3DWallLayoutCount(5, 3)).toBe(24);
    expect(resolveApplication3DWallLayoutCount(24, 2)).toBe(24);
    expect(resolveApplication3DWallLayoutCount(10, 1)).toBe(10);
    expect(resolveApplication3DWallLayoutCount(0, 0)).toBe(0);
  });
});
