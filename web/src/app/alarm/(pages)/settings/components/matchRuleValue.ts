export type MatchRuleScalar = string | number;
export type MatchRuleValue =
  | MatchRuleScalar
  | MatchRuleScalar[]
  | undefined;

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

export const isEmptyMatchRuleValue = (value: MatchRuleValue) =>
  value === undefined ||
  value === '' ||
  (Array.isArray(value) && value.length === 0);
