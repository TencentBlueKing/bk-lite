import {
  COMPARE_TARGET_LIST,
  LEGACY_COMPARE_OFFSETS,
  MAX_COMPARE_OFFSET_DAYS,
  MAX_COMPARE_OFFSET_HOURS,
} from '@/app/log/constants';
import { PolicyCompare } from '@/app/log/types/integration';

type Translate = (key: string, fallback?: string, vars?: Record<string, unknown>) => string;

export const presentCompare = (compare?: PolicyCompare): PolicyCompare => {
  const kind = compare?.kind || 'absolute';
  if (kind === 'absolute') {
    return { kind: 'absolute' };
  }
  const legacy = compare?.to ? LEGACY_COMPARE_OFFSETS[compare.to] : undefined;
  if (legacy) {
    return { kind, to: legacy.to, offset: legacy.offset };
  }
  return { kind, to: compare?.to, offset: compare?.offset };
};

export const compareOffsetLimit = (target?: string) =>
  target === 'offset_days' ? MAX_COMPARE_OFFSET_DAYS : MAX_COMPARE_OFFSET_HOURS;

export const compareOffsetReady = (compare?: PolicyCompare) => {
  const presented = presentCompare(compare);
  if (presented.kind === 'absolute') {
    return true;
  }
  if (!presented.to) {
    return false;
  }
  if (presented.to !== 'offset_hours' && presented.to !== 'offset_days') {
    return true;
  }
  const offset = presented.offset;
  return Number.isInteger(offset) && (offset as number) >= 1 && (offset as number) <= compareOffsetLimit(presented.to);
};

/** 条件上的对照，或试算基线键 offset_hours:24。 */
export const formatCompareTarget = (
  target: string | undefined,
  offset: number | undefined,
  t: Translate,
) => {
  const keyed = target ? /^(offset_hours|offset_days):(\d+)$/.exec(target) : null;
  const family = keyed?.[1] || target;
  const count = keyed ? Number(keyed[2]) : offset;
  if (family === 'offset_hours' && count) {
    return t('log.event.compareOffsetHoursValue', undefined, { count });
  }
  if (family === 'offset_days' && count) {
    return t('log.event.compareOffsetDaysValue', undefined, { count });
  }
  const item = COMPARE_TARGET_LIST.find((entry) => entry.value === family);
  return item ? t(item.labelKey) : target || '';
};
