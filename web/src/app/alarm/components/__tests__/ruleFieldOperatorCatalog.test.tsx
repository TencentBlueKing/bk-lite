import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import contract from '../../../../../../specs/changes/alert-rule-types/field-operator-test-matrix.json';
import MatchRule from '../../(pages)/settings/components/matchRule';
import { operatorTranslation, ruleFields, type RuleScope } from '../../utils/multivalueRules';
import alarmZh from '../../locales/zh.json';
import alarmEn from '../../locales/en.json';
import commonZh from '../../../../locales/zh.json';

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: translate }) }));
vi.mock('@/app/alarm/context/common', () => ({ useCommon: () => ({ levelMeta: {
  event: { list: [{ level_id: 1, level_display_name: '事件严重' }] },
  alert: { list: [{ level_id: 1, level_display_name: '告警严重' }] },
} }) }));
vi.mock('@/app/alarm/api/integration', () => ({
  useSourceApi: () => ({ getAlertSourceOptions: async () => [{ id: 7, name: 'Prometheus', source_id: 'prom' }] }),
}));
afterEach(cleanup);
beforeAll(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addListener: vi.fn(), removeListener: vi.fn() });
});

type ValueKind = 'text' | 'tags' | 'level' | 'source';
interface OperatorSpec { key: string; label: string; value: ValueKind }
interface FieldSpec { key: string; label: string; operators: OperatorSpec[] }

const TEXT: OperatorSpec[] = [
  { key: 'eq', label: '等于', value: 'text' },
  { key: 'ne', label: '不等于', value: 'text' },
  { key: 'contains', label: '包含', value: 'text' },
  { key: 'not_contains', label: '不包含', value: 'text' },
];
const CANDIDATE = (value: ValueKind): OperatorSpec[] => [
  { key: 'any_of', label: '包含', value },
  { key: 'none_of', label: '不包含', value },
];
const SET: OperatorSpec[] = [
  { key: 'any_of', label: '包含任一', value: 'source' },
  { key: 'all_of', label: '包含全部', value: 'source' },
  { key: 'none_of', label: '不包含', value: 'source' },
];
const MIXED: OperatorSpec[] = [
  { key: 'any_of', label: '属于任意一个', value: 'tags' },
  { key: 'none_of', label: '不属于任何一个', value: 'tags' },
  { key: 'contains', label: '文本包含', value: 'text' },
  { key: 'not_contains', label: '文本不包含', value: 'text' },
  { key: 're', label: '正则', value: 'text' },
];

/** 界面查询类型的独立期望：中文文案来自产品契约，不从生产目录或 i18n key 推导。 */
const EVENT_CATALOG: FieldSpec[] = [
  { key: 'title', label: '标题', operators: TEXT },
  { key: 'source_name', label: '告警源', operators: CANDIDATE('source') },
  { key: 'level', label: '级别', operators: CANDIDATE('level') },
  { key: 'resource_type', label: '类型对象', operators: CANDIDATE('tags') },
  { key: 'resource_id', label: '对象实例', operators: CANDIDATE('tags') },
  { key: 'description', label: '内容', operators: TEXT },
  { key: 'service', label: '服务', operators: MIXED },
  { key: 'location', label: '位置', operators: MIXED },
  { key: 'resource_name', label: '资源名称', operators: MIXED },
  { key: 'item', label: '指标', operators: MIXED },
  { key: 'push_source_id', label: '监控源', operators: CANDIDATE('tags') },
];
const ALERT_CATALOG: FieldSpec[] = [
  { key: 'title', label: '标题', operators: TEXT },
  { key: 'source_names', label: '告警源', operators: SET },
  { key: 'level', label: '级别', operators: CANDIDATE('level') },
  { key: 'resource_type', label: '类型对象', operators: CANDIDATE('tags') },
  { key: 'resource_id', label: '对象实例', operators: CANDIDATE('tags') },
  { key: 'content', label: '内容', operators: TEXT },
  { key: 'resource_name', label: '资源名称', operators: MIXED },
  { key: 'item', label: '指标', operators: MIXED },
  { key: 'push_source_ids', label: '监控源', operators: [
    { key: 'any_of', label: '包含任一', value: 'tags' },
    { key: 'all_of', label: '包含全部', value: 'tags' },
    { key: 'none_of', label: '不包含', value: 'tags' },
  ] },
];
const SCOPES: Record<RuleScope, FieldSpec[]> = {
  correlation: EVENT_CATALOG,
  shield: EVENT_CATALOG,
  enrichment: EVENT_CATALOG,
  assignment: ALERT_CATALOG,
  action: ALERT_CATALOG,
};

function lookup(root: unknown, key: string) {
  return key.split('.').reduce<unknown>((current, part) => (
    current && typeof current === 'object' ? (current as Record<string, unknown>)[part] : undefined
  ), root);
}
function translate(key: string) {
  const value = lookup(alarmZh, key) ?? lookup(commonZh, key);
  return typeof value === 'string' ? value : key;
}
function optionLabels() {
  return Array.from(document.querySelectorAll('.ant-select-item-option-content')).map(node => node.textContent);
}
function valueKind(): ValueKind {
  if (screen.queryByRole('combobox', { name: '选择告警源' })) return 'source';
  if (screen.queryByRole('combobox', { name: '匹配值' })) return 'tags';
  if (document.querySelector('.ant-select-multiple')) return 'level';
  if (screen.queryByPlaceholderText('请输入')) return 'text';
  throw new Error('无法识别值控件');
}

const fieldCases = (Object.entries(SCOPES) as [RuleScope, FieldSpec[]][]).flatMap(([scope, catalog]) =>
  catalog.map(field => ({ scope, field })));
const operatorCases = fieldCases.flatMap(({ scope, field }) =>
  field.operators.map(operator => ({ scope, field, operator })));

describe('告警筛选字段与查询类型目录', () => {
  it.each(Object.entries(SCOPES) as [RuleScope, FieldSpec[]][])('%s 字段列表、顺序与独立矩阵一致', (scope, catalog) => {
    const offered = ruleFields(scope);
    expect(offered.map(field => field.key)).toEqual(catalog.map(field => field.key));
    expect(Object.fromEntries(catalog.map(field => [field.key, field.operators.map(item => item.key)])))
      .toEqual(contract[scope === 'assignment' || scope === 'action' ? 'alert' : 'event']);
    render(<MatchRule scope={scope} levelType={scope === 'assignment' || scope === 'action' ? 'alert' : 'event'} />);
    fireEvent.mouseDown(screen.getAllByRole('combobox')[0]);
    expect(optionLabels()).toEqual(catalog.map(field => field.label));
  });

  it.each(operatorCases)('$scope / $field.label / $operator.label 条件菜单、中文文案和值控件', ({ scope, field, operator }) => {
    expect(translate(operatorTranslation(field.key, operator.key))).toBe(operator.label);
    expect(lookup(alarmEn, operatorTranslation(field.key, operator.key))).toEqual(expect.any(String));
    render(<MatchRule
      scope={scope}
      levelType={scope === 'assignment' || scope === 'action' ? 'alert' : 'event'}
      value={[[{ key: field.key, operator: operator.key, value: operator.value === 'text' ? '示例' : ['1'] }]]}
    />);
    fireEvent.mouseDown(screen.getAllByRole('combobox')[1]);
    expect(optionLabels()).toEqual(field.operators.map(item => item.label));
    fireEvent.keyDown(screen.getAllByRole('combobox')[1], { key: 'Escape', keyCode: 27 });
    expect(valueKind()).toBe(operator.value);
  });

  it.each(Object.entries(SCOPES) as [RuleScope, FieldSpec[]][])('%s 字段说明覆盖全部字段与查询类型', (scope, catalog) => {
    render(<MatchRule scope={scope} levelType={scope === 'assignment' || scope === 'action' ? 'alert' : 'event'} />);
    fireEvent.click(screen.getByRole('button', { name: '字段与匹配说明' }));
    const help = document.querySelector('.ant-popover-inner')?.textContent || '';
    for (const field of catalog) {
      expect(help).toContain(field.label);
      for (const operator of field.operators) expect(help).toContain(operator.label);
    }
  });
});
