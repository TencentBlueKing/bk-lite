import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import MatchRule from '../../(pages)/settings/components/matchRule';
import { invalidMatchRules, ruleFields, isMultiOperator } from '../../utils/multivalueRules';

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/alarm/context/common', () => ({ useCommon: () => ({ levelMeta: {event:{list:[{level_id:1,level_display_name:'严重'}]}} }) }));
vi.mock('@/app/alarm/api/integration', () => ({ useSourceApi: () => ({ getAlertSourceOptions: async () => [{id:7,name:'Prometheus'}] }) }));
afterEach(cleanup);
beforeAll(() => { window.matchMedia = vi.fn().mockReturnValue({matches:false, addListener:vi.fn(),removeListener:vi.fn()}); });

const scopes = ['correlation','assignment','shield','enrichment','action'] as const;
describe('字段类型决定编辑控件及可用操作符', () => {
  it.each(scopes)('%s 标题只有四个单值操作符', async scope => {
    const onChange = vi.fn();
    render(<MatchRule scope={scope} value={[[{key:'title',operator:'eq',value:'CPU'}]]} onChange={onChange} />);
    fireEvent.mouseDown(screen.getAllByRole('combobox')[1]);
    const options = Array.from(document.querySelectorAll('.ant-select-item-option-content')).map(node => node.textContent);
    expect(options).toEqual(['eq','ne','contains','not_contains'].map(op => `alarmCommon.sourceOperators.${op}`));
    fireEvent.change(screen.getByDisplayValue('CPU'), {target:{value:'CPU, disk busy'}});
    expect(onChange).toHaveBeenLastCalledWith([[{key:'title',operator:'eq',value:'CPU, disk busy'}]]);
    expect(screen.queryByRole('combobox',{name:'alarmCommon.multiValueInput'})).toBeNull();
  });
  it.each(['assignment','action'] as const)('%s 列表支持任一、全部、不含任一，切换保留数组', async scope => {
    const onChange = vi.fn();
    render(<MatchRule scope={scope} value={[[{key:'push_source_ids',operator:'all_of',value:['a','b']}]]} onChange={onChange} />);
    fireEvent.mouseDown(screen.getAllByRole('combobox')[1]);
    expect(Array.from(document.querySelectorAll('.ant-select-item-option-content')).map(node => node.textContent)).toEqual([
      'alarmCommon.multiOperators.any_ofList','alarmCommon.multiOperators.all_of','alarmCommon.multiOperators.none_ofList']);
    fireEvent.click(screen.getByText('alarmCommon.multiOperators.any_ofList'));
    expect(onChange).toHaveBeenLastCalledWith([[{key:'push_source_ids',operator:'any_of',value:['a','b']}]]);
    const input=screen.getByRole('combobox',{name:'alarmCommon.multiValueInput'});
    fireEvent.change(input,{target:{value:'001'}});fireEvent.keyDown(input,{key:'Enter',keyCode:13});
    expect(onChange).toHaveBeenLastCalledWith([[{key:'push_source_ids',operator:'any_of',value:['a','b','001']}]]);
  });
  it.each(['source_pk','level_id','source_id'])('Alert 不补入无效字段 %s', async key => {
    render(<MatchRule scope="assignment" value={[[{key,operator:'eq',value:'1'}]]} />);
    expect(screen.getByRole('alert').textContent).toBe('alarmCommon.invalidRuleCondition');
    fireEvent.mouseDown(screen.getAllByRole('combobox')[0]);
    expect(screen.queryByText(key)).toBeNull();
    expect(invalidMatchRules([[{key,operator:'eq',value:'1'}]],false,'assignment')).toBe(true);
  });
  it.each(scopes)('%s 目录全部字段都能通过各自的合法值校验', scope => {
    for (const field of ruleFields(scope)) for (const operator of field.operators) {
      const value=isMultiOperator(operator)?['a','b']:'1';
      expect(invalidMatchRules([[{key:field.key,operator,value}]],false,scope)).toBe(false);
      expect(invalidMatchRules([[{key:field.key,operator,value:isMultiOperator(operator)?'a':[value]}]],false,scope)).toBe(true);
    }
  });
});
