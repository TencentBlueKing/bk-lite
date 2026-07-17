export type MatchRuleScalar = string | number;
export type MatchRuleValue =
  | MatchRuleScalar
  | MatchRuleScalar[]
  | undefined;

export interface MatchRuleOperatorOption {
  name: string;
  desc: string;
}

export const LEVEL_MULTI_OPERATOR_OPTIONS = [
  { name: 'eq', desc: '等于' },
  { name: 'ne', desc: '不等于' },
] as const;

export const isLevelMultiSelectEnabled = (
  key: string | undefined,
  enabled: boolean,
) => enabled && key === 'level';

export const normalizeMultipleRuleValue = (
  value: MatchRuleValue,
): MatchRuleScalar[] => {
  if (value === undefined || value === '') return [];
  return Array.isArray(value) ? value : [value];
};

export const getMatchRuleOperatorOptions = (
  key: string | undefined,
  enabled: boolean,
  fallbackOptions: readonly MatchRuleOperatorOption[],
) =>
  isLevelMultiSelectEnabled(key, enabled)
    ? LEVEL_MULTI_OPERATOR_OPTIONS
    : fallbackOptions;

export const getMatchRuleValueSelectState = (
  key: string | undefined,
  enabled: boolean,
  value: MatchRuleValue,
) =>
  isLevelMultiSelectEnabled(key, enabled)
    ? { mode: 'multiple' as const, value: normalizeMultipleRuleValue(value) }
    : { mode: undefined, value };

export const getMatchRuleValueAfterOperatorChange = (
  key: string | undefined,
  enabled: boolean,
  value: MatchRuleValue,
) => (isLevelMultiSelectEnabled(key, enabled) ? undefined : value);

export const isEmptyMatchRuleValue = (value: unknown) =>
  (!value && value !== 0) ||
  (Array.isArray(value) && value.length === 0);
