import type { Application3DWallItem } from '@/app/ops-analysis/types/sceneWidget';

export const APPLICATION3D_WALL_PAGE_SIZE = 24;

const stateRank = (item: Application3DWallItem) => {
  if (item.health.state === 'alarming') return 2;
  if (item.health.state === 'unknown') return 1;
  return 0;
};

const severityRank = (item: Application3DWallItem) =>
  item.health.highestSeverity?.rank ?? 0;

const alarmCount = (item: Application3DWallItem) =>
  item.health.activeAlarmCount ?? 0;

export const sortApplication3DWallItems = (
  items: Application3DWallItem[],
): Application3DWallItem[] =>
  [...items].sort((left, right) => {
    const stateDelta = stateRank(right) - stateRank(left);
    if (stateDelta !== 0) return stateDelta;
    if (left.health.state === 'alarming') {
      const severityDelta = severityRank(right) - severityRank(left);
      if (severityDelta !== 0) return severityDelta;
      const countDelta = alarmCount(right) - alarmCount(left);
      if (countDelta !== 0) return countDelta;
    }
    const nameDelta = left.name.localeCompare(right.name, 'zh-CN');
    if (nameDelta !== 0) return nameDelta;
    return left.id.localeCompare(right.id);
  });

export const paginateApplication3DWallItems = (
  items: Application3DWallItem[],
  page: number,
  pageSize = APPLICATION3D_WALL_PAGE_SIZE,
) => {
  const totalCount = items.length;
  const totalPages = Math.ceil(totalCount / pageSize);
  const safePage = totalPages === 0 ? 1 : Math.min(Math.max(Math.trunc(page) || 1, 1), totalPages);
  const start = (safePage - 1) * pageSize;
  return {
    pageItems: items.slice(start, start + pageSize),
    page: safePage,
    totalPages,
    totalCount,
    hasPrev: safePage > 1 && totalPages > 1,
    hasNext: safePage < totalPages,
  };
};

/** Paginated walls keep the full-page (24) density, camera, and grid frame. */
export const resolveApplication3DWallLayoutCount = (
  visibleCount: number,
  totalPages: number,
  pageSize = APPLICATION3D_WALL_PAGE_SIZE,
) => (totalPages > 1 ? pageSize : visibleCount);
