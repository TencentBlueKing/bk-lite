import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import { normalizeInputConfig } from '@/app/ops-analysis/utils/paramInputConfigUtils';

/** 文本/数字写进选项查询签名前的尾随等待。下拉和单选不走这条路径。 */
export const OPTIONS_QUERY_TEXT_DEBOUNCE_MS = 300;

/** 空文本/数字应立刻挡住选项查询，不能再等防抖。 */
export const isOptionsQueryTextEmpty = (value: unknown): boolean => (
  value == null || value === ''
);

/**
 * 组件参数里会逐字变化、并可能被下游选项查询读走的控件。
 * 下拉、单选、组织树和日期是一次选定，不防抖。
 */
export const isFreeTextOptionsParam = (
  param: Pick<ParamItem, 'type' | 'inputConfig' | 'inputMode' | 'options'>,
): boolean => {
  const config = normalizeInputConfig(param);
  if (config && config.control !== 'input') return false;
  const type = param.type || 'string';
  return type === 'string' || type === 'number';
};

/**
 * 筛选栏里会逐字变化的上游。数字框和普通文本框（含多行）算在内。
 * 下拉、单选、组织树保持选定后立刻重载下游候选项。
 */
export const isFreeTextOptionsFilter = (
  definition: Pick<UnifiedFilterDefinition, 'type' | 'inputMode' | 'inputConfig' | 'options'>,
): boolean => {
  if (definition.type === 'number') return true;
  if (definition.type !== 'string') return false;
  if (
    definition.inputMode === 'select'
    || definition.inputMode === 'radio'
    || definition.inputMode === 'organization'
  ) {
    return false;
  }
  const config = normalizeInputConfig(definition);
  if (config && config.control !== 'input') return false;
  return true;
};
