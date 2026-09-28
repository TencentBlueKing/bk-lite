import { describe, expect, it } from 'vitest';
import type { Application3DHealth, Application3DWallItem } from '@/app/ops-analysis/types/sceneWidget';
import {
  APPLICATION3D_WALL_PAGE_SIZE,
  paginateApplication3DWallItems,
  planApplication3DWallPages,
  resolveApplication3DWallPageAfterRefresh,
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

  it('keeps one queue and the 24-card page when alarm pages are off', () => {
    const alarming = item('a', '告警', health({
      state: 'alarming',
      highestSeverity: { id: 'critical', label: '严重', rank: 400, color: 'critical' },
    }));
    const unknown = item('u', '未知', health({ state: 'unknown' }));
    const normal = item('n', '正常', health({ state: 'normal' }));
    const plan = planApplication3DWallPages([normal, unknown, alarming], 1);
    expect(plan.pageItems.map((entry) => entry.id)).toEqual(['a', 'u', 'n']);
    expect(plan.section).toBe('rest');
    expect(plan.layoutCount).toBe(3);
  });

  it('puts only alarming systems on leading pages and does not backfill the last alarm page', () => {
    const alarms = Array.from({ length: 3 }, (_, index) => item(
      `a-${index}`,
      `告警${index}`,
      health({
        state: 'alarming',
        activeAlarmCount: index + 1,
        highestSeverity: { id: 'warning', label: '警告', rank: 200, color: 'warning' },
      }),
    ));
    const unknown = item('u', '未知', health({ state: 'unknown' }));
    const normals = Array.from({ length: 4 }, (_, index) => item(
      `n-${index}`,
      `正常${index}`,
      health({ state: 'normal' }),
    ));
    const config = { alarmPagesEnabled: true, alarmPageSize: 2, pageSize: 3 };
    const first = planApplication3DWallPages([...normals, unknown, ...alarms], 1, config);
    expect(first.section).toBe('alarm');
    expect(first.pageItems.map((entry) => entry.id)).toEqual(['a-2', 'a-1']);
    expect(first.layoutCount).toBe(2);
    expect(first.totalPages).toBe(4);

    const second = planApplication3DWallPages([...normals, unknown, ...alarms], 2, config);
    expect(second.section).toBe('alarm');
    expect(second.pageItems.map((entry) => entry.id)).toEqual(['a-0']);
    expect(second.layoutCount).toBe(2);
    expect(second.pageItems.map((entry) => entry.id)).not.toContain('u');

    const third = planApplication3DWallPages([...normals, unknown, ...alarms], 3, config);
    expect(third.section).toBe('rest');
    expect(third.pageItems.map((entry) => entry.id)).toEqual(['u', 'n-0', 'n-1']);
    expect(third.layoutCount).toBe(3);
  });

  it('starts on the rest section when nothing is alarming', () => {
    const plan = planApplication3DWallPages(
      [item('n', '正常', health({ state: 'normal' }))],
      1,
      { alarmPagesEnabled: true, alarmPageSize: 8 },
    );
    expect(plan.alarmPageCount).toBe(0);
    expect(plan.page).toBe(1);
    expect(plan.section).toBe('rest');
    expect(plan.pageItems.map((entry) => entry.id)).toEqual(['n']);
    expect(plan.totalPages).toBe(1);
  });

  it('sizes a one-page section to the cards it has and locks a short later page to the section size', () => {
    const alarms = [item('a', '告警', health({
      state: 'alarming',
      highestSeverity: { id: 'error', label: '错误', rank: 300, color: 'danger' },
    }))];
    const normals = Array.from({ length: 5 }, (_, index) => item(
      `n-${index}`,
      `正常${index}`,
      health({ state: 'normal' }),
    ));
    const config = { alarmPagesEnabled: true, alarmPageSize: 24, pageSize: 2 };
    const alarmPage = planApplication3DWallPages([...alarms, ...normals], 1, config);
    expect(alarmPage.sectionPageCount).toBe(1);
    expect(alarmPage.layoutCount).toBe(1);

    const lastRest = planApplication3DWallPages([...alarms, ...normals], 4, config);
    expect(lastRest.section).toBe('rest');
    expect(lastRest.pageItems).toHaveLength(1);
    expect(lastRest.sectionPageCount).toBe(3);
    expect(lastRest.layoutCount).toBe(2);
  });

  it('stays in the rest section when a refresh adds an alarm page in front', () => {
    const alarm = (id: string) => item(id, id, health({
      state: 'alarming',
      highestSeverity: { id: 'warning', label: '警告', rank: 200, color: 'warning' },
    }));
    const normal = (id: string) => item(id, id, health({ state: 'normal' }));
    const before = [
      ...Array.from({ length: 10 }, (_, index) => alarm(`a-${index}`)),
      ...Array.from({ length: 30 }, (_, index) => normal(`n-${index}`)),
    ];
    const viewing = planApplication3DWallPages(before, 2, {
      alarmPagesEnabled: true,
      alarmPageSize: 24,
      pageSize: 24,
    });
    expect(viewing.section).toBe('rest');
    expect(viewing.sectionPage).toBe(1);

    const after = [
      ...Array.from({ length: 30 }, (_, index) => alarm(`a-${index}`)),
      ...Array.from({ length: 30 }, (_, index) => normal(`n-${index}`)),
    ];
    const page = resolveApplication3DWallPageAfterRefresh(after, {
      section: viewing.section!,
      sectionPage: viewing.sectionPage,
    }, { alarmPagesEnabled: true, alarmPageSize: 24, pageSize: 24 });
    const restored = planApplication3DWallPages(after, page, {
      alarmPagesEnabled: true,
      alarmPageSize: 24,
      pageSize: 24,
    });
    expect(restored.section).toBe('rest');
    expect(restored.sectionPage).toBe(1);
    expect(restored.pageItems.every((entry) => entry.health.state === 'normal')).toBe(true);
  });

  it('lands on the first rest page when the alarm section disappears', () => {
    const page = resolveApplication3DWallPageAfterRefresh(
      [item('n', '正常', health({ state: 'normal' }))],
      { section: 'alarm', sectionPage: 1 },
      { alarmPagesEnabled: true },
    );
    expect(page).toBe(1);
    const plan = planApplication3DWallPages(
      [item('n', '正常', health({ state: 'normal' }))],
      page,
      { alarmPagesEnabled: true },
    );
    expect(plan.section).toBe('rest');
  });
});
