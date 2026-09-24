import type { Application3DWallItem } from '@/app/ops-analysis/types/sceneWidget';
import type { Application3DWallConfig } from '@/app/ops-analysis/utils/application3DWallConfig';
import { resolveApplication3DWallConfig } from '@/app/ops-analysis/utils/application3DWallConfig';

export const APPLICATION3D_WALL_PAGE_SIZE = 24;

export type Application3DWallSectionName = 'alarm' | 'rest';

export interface Application3DWallSectionPlace {
  section: Application3DWallSectionName;
  sectionPage: number;
}

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

/** A section with several pages keeps the full-page grid; a one-page section sizes to the cards it has. */
export const resolveApplication3DWallLayoutCount = (
  visibleCount: number,
  sectionPageCount: number,
  pageSize = APPLICATION3D_WALL_PAGE_SIZE,
) => (sectionPageCount > 1 ? pageSize : visibleCount);

const pageCountFor = (count: number, pageSize: number) => (
  count <= 0 ? 0 : Math.ceil(count / pageSize)
);

const slicePage = (items: Application3DWallItem[], sectionPage: number, pageSize: number) => {
  const start = (sectionPage - 1) * pageSize;
  return items.slice(start, start + pageSize);
};

export interface Application3DWallPagePlan {
  pageItems: Application3DWallItem[];
  page: number;
  totalPages: number;
  totalCount: number;
  hasPrev: boolean;
  hasNext: boolean;
  section: Application3DWallSectionName | null;
  sectionPage: number;
  sectionPageCount: number;
  layoutCount: number;
  alarmPageCount: number;
  restPageCount: number;
}

const emptyPlan = (): Application3DWallPagePlan => ({
  pageItems: [],
  page: 1,
  totalPages: 0,
  totalCount: 0,
  hasPrev: false,
  hasNext: false,
  section: null,
  sectionPage: 1,
  sectionPageCount: 0,
  layoutCount: 0,
  alarmPageCount: 0,
  restPageCount: 0,
});

/**
 * Alarm pages, when enabled, hold only alarming systems. Unknown and normal
 * follow on their own pages and do not backfill a short alarm page.
 */
export const planApplication3DWallPages = (
  items: Application3DWallItem[],
  page: number,
  rawConfig?: Partial<Application3DWallConfig> | null,
): Application3DWallPagePlan => {
  const config = resolveApplication3DWallConfig(rawConfig);
  const sorted = sortApplication3DWallItems(items);
  const alarmItems = config.alarmPagesEnabled
    ? sorted.filter((item) => item.health.state === 'alarming')
    : [];
  const restItems = config.alarmPagesEnabled
    ? sorted.filter((item) => item.health.state !== 'alarming')
    : sorted;
  const alarmPageCount = pageCountFor(alarmItems.length, config.alarmPageSize);
  const restPageCount = pageCountFor(restItems.length, config.pageSize);
  const totalPages = alarmPageCount + restPageCount;
  const totalCount = sorted.length;
  if (totalPages === 0) return emptyPlan();

  const safePage = Math.min(Math.max(Math.trunc(page) || 1, 1), totalPages);
  const inAlarm = safePage <= alarmPageCount;
  const sectionPage = inAlarm ? safePage : safePage - alarmPageCount;
  const sectionPageCount = inAlarm ? alarmPageCount : restPageCount;
  const pageSize = inAlarm ? config.alarmPageSize : config.pageSize;
  const source = inAlarm ? alarmItems : restItems;
  const pageItems = slicePage(source, sectionPage, pageSize);
  return {
    pageItems,
    page: safePage,
    totalPages,
    totalCount,
    hasPrev: safePage > 1,
    hasNext: safePage < totalPages,
    section: inAlarm ? 'alarm' : 'rest',
    sectionPage,
    sectionPageCount,
    layoutCount: resolveApplication3DWallLayoutCount(
      pageItems.length,
      sectionPageCount,
      pageSize,
    ),
    alarmPageCount,
    restPageCount,
  };
};

/** Keep the viewer in the same section after a refresh, instead of the same global page number. */
export const resolveApplication3DWallPageAfterRefresh = (
  items: Application3DWallItem[],
  place: Application3DWallSectionPlace | null,
  rawConfig?: Partial<Application3DWallConfig> | null,
): number => {
  const probe = planApplication3DWallPages(items, 1, rawConfig);
  if (!place || probe.totalPages === 0) return 1;
  if (place.section === 'alarm') {
    if (probe.alarmPageCount === 0) return 1;
    return Math.min(Math.max(place.sectionPage, 1), probe.alarmPageCount);
  }
  if (probe.restPageCount === 0) return Math.max(probe.alarmPageCount, 1);
  return probe.alarmPageCount + Math.min(Math.max(place.sectionPage, 1), probe.restPageCount);
};
