import { RULE_FIELDS } from '@/app/alarm/constants/rule-fields.generated';

export type RuleScope = 'correlation' | 'assignment' | 'shield' | 'enrichment' | 'action';
export interface RuleCondition { key?: string; operator?: string; value?: string | number | (string | number)[] }
export const MULTI_OPERATORS = ['any_of', 'all_of', 'none_of'];
export const isMultiOperator = (operator?: string) => MULTI_OPERATORS.includes(operator || '');
export const ruleFields = (scope: RuleScope) => RULE_FIELDS.filter(field =>
  (field.contexts as readonly string[]).includes(['assignment', 'action'].includes(scope) ? 'alert' : 'event'));
export const ruleField = (key?: string, scope?: RuleScope) => (scope ? ruleFields(scope) : RULE_FIELDS).find(field => field.key === key);
export const multiOperators = (key?: string) => ruleField(key)?.operators.filter(op => isMultiOperator(op)) || [];
export const normalizeRuleTags = (values: string[]) => Array.from(new Set(values.map(value => value.trim()).filter(Boolean)));
export const operatorTranslation = (key: string | undefined, operator: string) => {
  const field = ruleField(key);
  if (isMultiOperator(operator)) {
    if (field?.type === 'list') return `alarmCommon.multiOperators.${operator}${operator === 'all_of' ? '' : 'List'}`;
    if (field?.role === 'text') return `alarmCommon.multiOperators.${operator}`;
    return `alarmCommon.candidateOperators.${operator}`;
  }
  if (field?.operators.some(op => isMultiOperator(op)) && ['contains', 'not_contains'].includes(operator)) {
    return operator === 'contains' ? 'alarmCommon.textContains' : 'alarmCommon.textNotContains';
  }
  return `alarmCommon.sourceOperators.${operator}`;
};

export const invalidRuleCondition = (condition: RuleCondition, scope?: RuleScope) => {
  const { key, operator, value } = condition;
  const field = ruleField(key, scope);
  if (!field || !operator || !(field.operators as readonly string[]).includes(operator)) return true;
  if (isMultiOperator(operator)) return !Array.isArray(value) || !value.length || value.length > 50 ||
    value.some(item => typeof item !== 'string' || !item.trim() || item.length > 256);
  if (typeof value !== 'string' || !value.trim() || value.length > 256) return true;
  if (operator === 're') {
    try { new RegExp(value); } catch { return true; }
  }
  return false;
};
export const invalidMatchRules = (value: unknown, allowAll = false, scope?: RuleScope): boolean => {
  if (!Array.isArray(value) || value.length > 20 || (!allowAll && !value.length)) return true;
  if (value.reduce((count, group) => count + (Array.isArray(group) ? group.length : 101), 0) > 100) return true;
  return value.some(group => !Array.isArray(group) || !group.length || group.some(item => !item || typeof item !== 'object' || invalidRuleCondition(item, scope)));
};

export const formatMatchRules = (rules: RuleCondition[][], t: (key: string) => string) =>
  rules.map(group => `(${group.map(condition => {
    if (invalidRuleCondition(condition)) return t('alarmCommon.invalidRuleCondition');
    const label = t(`alarmCommon.ruleFields.${condition.key}`);
    const operator = t(operatorTranslation(condition.key, condition.operator!));
    return `${label} ${operator} ${JSON.stringify(condition.value)}`;
  }).join(` ${t('common.and')} `)})`).join(` ${t('common.or')} `);
