import type { FilterValue, UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { InputOption } from '@/app/ops-analysis/types/dataSource';
import { isOptionInputControl } from '@/app/ops-analysis/utils/paramInputConfigUtils';

const optionKey = (value: string | number): string => `${typeof value}:${String(value)}`;

export const isDynamicOptionFilter = (
  definition: Pick<UnifiedFilterDefinition, 'inputConfig'>,
): boolean => {
  const config = definition.inputConfig;
  return Boolean(
    config
    && isOptionInputControl(config)
    && config.optionsSource.type === 'dynamic',
  );
};

/** 只保留当前选项列表里真实存在的值；一个都对不上时清空。 */
export const retainFilterValueInOptions = (
  value: FilterValue | null | undefined,
  options: Array<Pick<InputOption, 'value'>>,
): FilterValue => {
  const keys = new Set(options.map((option) => optionKey(option.value)));
  const keep = (item: string | number) => keys.has(optionKey(item));

  if (Array.isArray(value)) {
    const kept = value.filter(
      (item): item is string | number =>
        (typeof item === 'string' || typeof item === 'number') && keep(item),
    );
    return kept.length ? kept : null;
  }
  if (typeof value === 'string' || typeof value === 'number') {
    return keep(value) ? value : null;
  }
  return value ?? null;
};

const valuesEqual = (
  left: FilterValue | null | undefined,
  right: FilterValue | null | undefined,
): boolean => {
  if (Array.isArray(left) || Array.isArray(right)) {
    if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
      return false;
    }
    return left.every((item, index) => item === right[index]);
  }
  return (left ?? null) === (right ?? null);
};

/**
 * 用选项列表校正筛选值。当前值为空时，回退到定义上的默认值再校正。
 * 没有变化时返回 undefined。
 */
export const reconcileOptionBackedFilterValue = (
  definition: Pick<UnifiedFilterDefinition, 'defaultValue'>,
  current: FilterValue | null | undefined,
  options: Array<Pick<InputOption, 'value'>>,
): FilterValue | undefined => {
  const source = current === undefined || current === null
    ? (definition.defaultValue ?? null)
    : current;
  const retained = retainFilterValueInOptions(source, options);
  if (valuesEqual(retained, current ?? null)) return undefined;
  return retained;
};

/** 打开画布时先不套用动态选项默认值，等当前用户的选项列表回来再校正。 */
export const deferDynamicOptionFilterValues = (
  definitions: UnifiedFilterDefinition[],
  values: Record<string, FilterValue>,
): Record<string, FilterValue> => {
  let changed = false;
  const next = { ...values };
  definitions.forEach((definition) => {
    if (!isDynamicOptionFilter(definition)) return;
    if (next[definition.id] == null) return;
    next[definition.id] = null;
    changed = true;
  });
  return changed ? next : values;
};
