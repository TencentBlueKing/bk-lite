import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import contract from '../../../../../../specs/changes/alert-rule-types/field-operator-test-matrix.json';
import MatchRule, { type MatchRuleProps } from '../../(pages)/settings/components/matchRule';
import { invalidMatchRules, ruleFields, type RuleScope } from '../../utils/multivalueRules';

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/alarm/context/common', () => ({ useCommon: () => ({ levelMeta: {
  event: { list: [{ level_id: 1, level_display_name: '事件严重' }, { level_id: 2, level_display_name: '事件预警' }] },
  alert: { list: [{ level_id: 1, level_display_name: '告警严重' }, { level_id: 2, level_display_name: '告警预警' }] },
} }) }));
afterEach(cleanup);
beforeAll(() => { window.matchMedia = vi.fn().mockReturnValue({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }); });

const scopes: Record<RuleScope, 'event' | 'alert'> = {
  correlation: 'event', shield: 'event', enrichment: 'event', assignment: 'alert', action: 'alert',
};
const cases = Object.entries(scopes).flatMap(([scope, context]) => Object.entries(contract[context]).flatMap(([key, ops]) =>
  ops.map(operator => ({ scope: scope as RuleScope, context, key, operator, ops }))));
const setOps = ['any_of', 'all_of', 'none_of'];
const mixed = ['resource_name', 'item', 'service', 'location'];
const listFields = ['source_names', 'push_source_ids'];
// 文案期望由已确认的业务矩阵独立给出，不调用被测 operatorTranslation。
function expectedLabel(key: string, operator: string) {
  if (setOps.includes(operator)) {
    if (listFields.includes(key)) return `alarmCommon.multiOperators.${operator}${operator === 'all_of' ? '' : 'List'}`;
    return `alarmCommon.${mixed.includes(key) ? 'multiOperators' : 'candidateOperators'}.${operator}`;
  }
  if (mixed.includes(key) && operator === 'contains') return 'alarmCommon.textContains';
  if (mixed.includes(key) && operator === 'not_contains') return 'alarmCommon.textNotContains';
  return `alarmCommon.sourceOperators.${operator}`;
}

describe('独立业务矩阵：五入口 × 每个字段 × 每种条件', () => {
  it.each(Object.keys(scopes) as RuleScope[])('%s 不遗漏字段，也不额外开放条件', scope => {
    expect(Object.fromEntries(ruleFields(scope).map(field => [field.key, [...field.operators]]))).toEqual(contract[scopes[scope]]);
  });

  it.each(cases)('$scope / $key / $operator 控件、条件菜单、修改提交和重开回显', ({ scope, context, key, operator, ops }) => {
    const multi = setOps.includes(operator);
    const initial = key === 'level' ? ['1'] : multi ? [`${key}:A`] : `${key}:初始正文`;
    const value: MatchRuleProps['value'] = [[{ key, operator, value: initial }]];
    const onChange = vi.fn();
    const editor = render(<MatchRule scope={scope} levelType={context} value={value} onChange={onChange} />);
    expect(screen.queryByRole('alert')).toBeNull();
    fireEvent.mouseDown(screen.getAllByRole('combobox')[1]);
    expect(Array.from(document.querySelectorAll('.ant-select-item-option-content')).map(node => node.textContent))
      .toEqual(ops.map(op => expectedLabel(key, op)));
    fireEvent.keyDown(screen.getAllByRole('combobox')[1], { key: 'Escape', keyCode: 27 });

    let expectedValue: string | string[];
    if (key === 'level') {
      expect(document.querySelectorAll('.ant-select-multiple')).toHaveLength(1);
      fireEvent.mouseDown(screen.getAllByRole('combobox')[2]);
      fireEvent.click(screen.getByText(context === 'event' ? '事件预警' : '告警预警'));
      expectedValue = ['1', '2'];
    } else if (multi) {
      expect(document.querySelectorAll('.ant-select-multiple')).toHaveLength(1);
      const input = screen.getByRole('combobox', { name: 'alarmCommon.multiValueInput' });
      fireEvent.change(input, { target: { value: `${key}:B,生产` } });
      fireEvent.keyDown(input, { key: 'Enter', keyCode: 13 });
      expectedValue = [`${key}:A`, `${key}:B,生产`];
      expect(input.getAttribute('aria-expanded')).toBe('false');
    } else {
      expect(document.querySelector('.ant-select-multiple')).toBeNull();
      expectedValue = `${key}:修改,100%_*`;
      fireEvent.change(screen.getByDisplayValue(initial as string), { target: { value: expectedValue } });
    }
    const saved = [[{ key, operator, value: expectedValue }]];
    expect(onChange).toHaveBeenLastCalledWith(saved);
    expect(invalidMatchRules(saved, false, scope)).toBe(false);
    editor.unmount();
    render(<MatchRule scope={scope} levelType={context} value={saved} />);
    expect(screen.queryByRole('alert')).toBeNull();
    if (multi) {
      expect(Array.from(document.querySelectorAll('.ant-select-selection-item-content')).map(node => node.textContent))
        .toEqual(key === 'level' ? (context === 'event' ? ['事件严重', '事件预警'] : ['告警严重', '告警预警']) : expectedValue);
    } else {
      expect(screen.getByDisplayValue(expectedValue as string)).toBeTruthy();
    }
  });

  it.each(cases)('$scope / $key / $operator 拒绝错误 value、超限和非法 OR 分支', ({ scope, key, operator }) => {
    const multi = setOps.includes(operator);
    const wanted = multi ? ['1', '2'] : '1';
    const valid = { key, operator, value: wanted };
    const invalid: unknown[] = [undefined, null, true, 1, {}, [], '', ' \t\n'];
    invalid.push(...(multi ? ['1', [null], [true], [1], [{}], [['1']], [''], [' \t'], ['x'.repeat(257)], Array(51).fill('1')]
      : [[wanted], 'x'.repeat(257), ...(operator === 're' ? ['['] : [])]));
    expect(invalidMatchRules([[valid]], false, scope)).toBe(false);
    for (const value of invalid) {
      expect(invalidMatchRules([[valid], [{ key, operator, value }]], false, scope), JSON.stringify(value)).toBe(true);
    }
  });
});
