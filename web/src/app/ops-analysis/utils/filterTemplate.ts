import dayjs from 'dayjs';

import type { DateRangeValue } from '@/app/ops-analysis/types/dateRange';
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { InputOption } from '@/app/ops-analysis/types/dataSource';
import { validateDateRangeValue } from '@/app/ops-analysis/utils/dateRange';
import { normalizeTimeRangeFilterValue } from '@/app/ops-analysis/utils/filterValue';
import {
  isOptionInputControl,
  normalizeInputConfig,
} from '@/app/ops-analysis/utils/paramInputConfigUtils';
import { isMultipleSelectInputConfig } from '@/app/ops-analysis/utils/stringParamMultipleMigrate';
import { isDynamicOptionFilter } from '@/app/ops-analysis/utils/optionBackedFilterValue';
import { isOrganizationFilterDefinition } from '@/app/ops-analysis/utils/unifiedFilterState';

const FILTER_TYPES = new Set(['string', 'number', 'timeRange', 'dateRange']);

/** 下拉右侧用英文类型。string 显示为 text，其余沿用筛选自己的类型名。 */
export const filterDropdownType = (type: UnifiedFilterDefinition['type']) => (
  type === 'string' ? 'text' : type
);

export interface FilterTemplateLabels {
  /** 动态选项加载完成后按筛选 id 填入。缺省表示还在加载。 */
  optionLabelsByFilterId: Record<string, Record<string, string> | undefined>;
  /** 缺省表示组织树还没就绪。空对象表示已加载但没有匹配组织。 */
  orgNamesById?: Record<string, string>;
  timeRangeLabels: Record<number, string>;
  dateRangeLabels: Record<string, string>;
  formatPair: (left: string, right: string) => string;
  formatMultiSelect: (first: string, count: number) => string;
}

export interface FilterTemplateVariable {
  definition: UnifiedFilterDefinition;
  token: string;
}

interface ParsedFilterToken {
  key: string;
  type?: UnifiedFilterDefinition['type'];
  end: number;
}

const isTokenBreak = (char: string | undefined) =>
  char === undefined || char === '$' || char === ':' || char === '\\' || /\s/.test(char);

const readFilterToken = (text: string, start: number): ParsedFilterToken | null => {
  let cursor = start + 1;
  let key = '';
  while (!isTokenBreak(text[cursor])) {
    key += text[cursor];
    cursor += 1;
  }
  if (!key) return null;

  if (text[cursor] === ':') {
    const typeStart = cursor + 1;
    const closing = text.indexOf('$', typeStart);
    if (closing < 0) return null;
    const type = text.slice(typeStart, closing);
    if (!FILTER_TYPES.has(type)) return null;
    return {
      key,
      type: type as UnifiedFilterDefinition['type'],
      end: closing + 1,
    };
  }

  if (text[cursor] !== '$') return null;
  return { key, end: cursor + 1 };
};

const enabledFilters = (definitions: UnifiedFilterDefinition[]) => {
  const grouped = new Map<string, Array<{ definition: UnifiedFilterDefinition; index: number }>>();
  definitions.forEach((definition, index) => {
    if (!definition.enabled || !definition.key) return;
    const peers = grouped.get(definition.key) ?? [];
    peers.push({ definition, index });
    grouped.set(definition.key, peers);
  });
  for (const peers of grouped.values()) {
    peers.sort(
      (left, right) => left.definition.order - right.definition.order || left.index - right.index,
    );
  }
  return grouped;
};

const tokenFor = (
  definition: UnifiedFilterDefinition,
  peers: Array<{ definition: UnifiedFilterDefinition }>,
) => (
  peers[0]?.definition.id === definition.id
    ? `$${definition.key}$`
    : `$${definition.key}:${definition.type}$`
);

export const listFilterTemplateVariables = (
  definitions: UnifiedFilterDefinition[],
): FilterTemplateVariable[] => {
  const grouped = enabledFilters(definitions);
  return definitions
    .map((definition, index) => ({ definition, index }))
    .filter((item) => item.definition.enabled && item.definition.key)
    .sort(
      (left, right) => left.definition.order - right.definition.order || left.index - right.index,
    )
    .map((item) => ({
      definition: item.definition,
      token: tokenFor(item.definition, grouped.get(item.definition.key) ?? []),
    }));
};

const findEnabledFilter = (
  definitions: UnifiedFilterDefinition[],
  key: string,
  type?: UnifiedFilterDefinition['type'],
) => {
  const peers = enabledFilters(definitions).get(key) ?? [];
  if (!peers.length) return undefined;
  if (type) return peers.find((item) => item.definition.type === type)?.definition;
  return peers[0]?.definition;
};

export const mapOptionLabels = (
  options: Array<Pick<InputOption, 'label' | 'value'>>,
): Record<string, string> => {
  const labels: Record<string, string> = {};
  options.forEach((option) => {
    if (!option.label) return;
    labels[String(option.value)] = option.label;
  });
  return labels;
};

const optionLabelMap = (
  definition: UnifiedFilterDefinition,
  labels: FilterTemplateLabels,
): Record<string, string> | undefined => {
  if (Object.prototype.hasOwnProperty.call(labels.optionLabelsByFilterId, definition.id)) {
    return labels.optionLabelsByFilterId[definition.id] ?? {};
  }
  const config = normalizeInputConfig(definition);
  if (isOptionInputControl(config) && config.optionsSource.type === 'static') {
    return mapOptionLabels(config.optionsSource.staticItems);
  }
  return undefined;
};

const scalarValues = (value: FilterValue): Array<string | number> => {
  if (Array.isArray(value)) {
    return value.filter(
      (item): item is string | number =>
        (typeof item === 'string' && item.length > 0)
        || (typeof item === 'number' && Number.isFinite(item)),
    );
  }
  if (typeof value === 'string' && value.length > 0) return [value];
  if (typeof value === 'number' && Number.isFinite(value)) return [value];
  return [];
};

const formatOptionNames = (
  names: string[],
  labels: FilterTemplateLabels,
): string | null => {
  if (!names.length || names.some((name) => !name)) return null;
  if (names.length === 1) return names[0] ?? null;
  if (names.length === 2) return labels.formatPair(names[0] ?? '', names[1] ?? '') || null;
  const formatted = labels.formatMultiSelect(names[0] ?? '', names.length);
  return formatted || null;
};

const renderOptionValue = (
  definition: UnifiedFilterDefinition,
  value: FilterValue,
  labels: FilterTemplateLabels,
): string | null => {
  const labelMap = optionLabelMap(definition, labels);
  if (!labelMap) return null;
  const config = normalizeInputConfig(definition);
  const multiple = isMultipleSelectInputConfig(config);
  const selected = scalarValues(value);
  if (!selected.length) return null;
  if (!multiple && selected.length !== 1) return null;
  const names = selected.map((item) => labelMap[String(item)] ?? '');
  if (names.some((name) => !name)) return null;
  return formatOptionNames(names, labels);
};

const hasClock = (
  value: dayjs.Dayjs,
  hour: number,
  minute: number,
  second: number,
) => value.hour() === hour && value.minute() === minute && value.second() === second;

/** 整天（开始 00:00:00，结束 23:59:59 或 00:00:00）只显示日期，其余精确到分钟。 */
const formatCustomTimeRange = (start: dayjs.Dayjs, end: dayjs.Dayjs) => {
  const wholeDay = hasClock(start, 0, 0, 0)
    && (hasClock(end, 23, 59, 59) || hasClock(end, 0, 0, 0));
  if (wholeDay) {
    return `${start.format('YYYY-MM-DD')} ~ ${end.format('YYYY-MM-DD')}`;
  }
  return `${start.format('YYYY-MM-DD HH:mm')} ~ ${end.format('YYYY-MM-DD HH:mm')}`;
};

const renderTimeRange = (
  value: FilterValue,
  labels: FilterTemplateLabels,
): string | null => {
  const normalized = normalizeTimeRangeFilterValue(value);
  if (!normalized?.start || !normalized.end) return null;
  if (typeof normalized.selectValue === 'number' && normalized.selectValue > 0) {
    return labels.timeRangeLabels[normalized.selectValue] || null;
  }
  const start = dayjs(normalized.start);
  const end = dayjs(normalized.end);
  if (!start.isValid() || !end.isValid()) return null;
  return formatCustomTimeRange(start, end);
};

const renderDateRange = (
  value: FilterValue,
  labels: FilterTemplateLabels,
): string | null => {
  if (value == null || !validateDateRangeValue(value).valid) return null;
  const dateValue = value as DateRangeValue;
  if (dateValue.rangeType === 'custom') {
    return `${dateValue.startDate} ~ ${dateValue.endDate}`;
  }
  return labels.dateRangeLabels[dateValue.rangeType] || null;
};

const renderOrganization = (
  value: FilterValue,
  labels: FilterTemplateLabels,
): string | null => {
  if (labels.orgNamesById === undefined) return null;
  const selected = scalarValues(value);
  if (selected.length !== 1) return null;
  return labels.orgNamesById[String(selected[0])] || null;
};

const renderScalar = (value: FilterValue): string | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  if (typeof value === 'string' && value.length > 0) return value;
  return null;
};

const renderFilterValue = (
  definition: UnifiedFilterDefinition,
  value: FilterValue | undefined,
  labels: FilterTemplateLabels,
): string | null => {
  if (value == null || value === '') return null;
  if (definition.type === 'timeRange') return renderTimeRange(value, labels);
  if (definition.type === 'dateRange') return renderDateRange(value, labels);
  if (isOrganizationFilterDefinition(definition)) return renderOrganization(value, labels);
  const config = normalizeInputConfig(definition);
  if (isOptionInputControl(config)) return renderOptionValue(definition, value, labels);
  if (definition.type === 'number' || definition.type === 'string') return renderScalar(value);
  return null;
};

const filterDisplayName = (definition: UnifiedFilterDefinition) =>
  definition.name?.trim() || definition.key;

/**
 * 文本里匹配不到当前启用筛选的 `$key$` / `$key:type$`。
 * `\$` 是字面量，不参与检测；同一个变量只返回一次。
 */
export interface FilterTemplateAsyncDependencies {
  dynamicFilterIds: string[];
  needsOrganization: boolean;
}

/** 标题里实际引用到的、需要等加载结束的筛选。 */
export const filterTemplateAsyncDependencies = (
  texts: string[],
  definitions: UnifiedFilterDefinition[],
): FilterTemplateAsyncDependencies => {
  const dynamic = new Set<string>();
  let needsOrganization = false;
  texts.forEach((text) => {
    if (!text) return;
    for (let cursor = 0; cursor < text.length; cursor += 1) {
      if (text[cursor] === '\\' && text[cursor + 1] === '$') {
        cursor += 1;
        continue;
      }
      if (text[cursor] !== '$') continue;
      const token = readFilterToken(text, cursor);
      if (!token) continue;
      cursor = token.end - 1;
      const definition = findEnabledFilter(definitions, token.key, token.type);
      if (!definition) continue;
      if (isDynamicOptionFilter(definition)) dynamic.add(definition.id);
      if (isOrganizationFilterDefinition(definition)) needsOrganization = true;
    }
  });
  return { dynamicFilterIds: [...dynamic], needsOrganization };
};

export const areFilterTemplateLabelsSettled = (
  dependencies: FilterTemplateAsyncDependencies,
  labels: Pick<FilterTemplateLabels, 'optionLabelsByFilterId' | 'orgNamesById'>,
) => {
  if (dependencies.needsOrganization && labels.orgNamesById === undefined) return false;
  return dependencies.dynamicFilterIds.every((id) =>
    Object.prototype.hasOwnProperty.call(labels.optionLabelsByFilterId, id),
  );
};

export const listUnmatchedFilterTokens = (
  text: string,
  definitions: UnifiedFilterDefinition[],
): string[] => {
  if (!text) return [];
  const unmatched: string[] = [];
  const seen = new Set<string>();
  for (let cursor = 0; cursor < text.length; cursor += 1) {
    if (text[cursor] === '\\' && text[cursor + 1] === '$') {
      cursor += 1;
      continue;
    }
    if (text[cursor] !== '$') continue;
    const token = readFilterToken(text, cursor);
    if (!token) continue;
    const raw = text.slice(cursor, token.end);
    cursor = token.end - 1;
    if (findEnabledFilter(definitions, token.key, token.type)) continue;
    if (seen.has(raw)) continue;
    seen.add(raw);
    unmatched.push(raw);
  }
  return unmatched;
};

/**
 * 把 `$key$` / `$key:type$` 换成已应用筛选的显示名。
 * 启用筛选没有值、还在加载或选项对不上时，显示筛选项名称。
 * 已删除或已禁用的变量保留原文；`\$` 只输出字面量 `$`。
 */
export const resolveFilterTemplate = (
  text: string,
  definitions: UnifiedFilterDefinition[],
  appliedValues: Record<string, FilterValue>,
  labels: FilterTemplateLabels,
): string => {
  if (!text) return '';
  let resolved = '';
  for (let cursor = 0; cursor < text.length; cursor += 1) {
    const current = text[cursor];
    if (current === '\\' && text[cursor + 1] === '$') {
      resolved += '$';
      cursor += 1;
      continue;
    }
    if (current !== '$') {
      resolved += current;
      continue;
    }
    const token = readFilterToken(text, cursor);
    if (!token) {
      resolved += current;
      continue;
    }
    const definition = findEnabledFilter(definitions, token.key, token.type);
    if (!definition) {
      resolved += text.slice(cursor, token.end);
      cursor = token.end - 1;
      continue;
    }
    resolved += renderFilterValue(definition, appliedValues[definition.id], labels)
      ?? filterDisplayName(definition);
    cursor = token.end - 1;
  }
  return resolved;
};
