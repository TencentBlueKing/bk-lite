import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';
import MatchRule from '../../(pages)/settings/components/matchRule';

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/alarm/context/common', () => ({ useCommon: () => ({ levelMeta: {event:{list:[{level_id:1,level_display_name:'严重'},{level_id:2,level_display_name:'预警'}]}} }) }));
vi.mock('@/app/alarm/api/integration', () => ({ useSourceApi: () => ({ getAlertSourceOptions: async () => [] }) }));
afterEach(cleanup);
beforeAll(() => { window.matchMedia = vi.fn().mockReturnValue({matches:false, addListener:vi.fn(),removeListener:vi.fn()}); });

it.each(['correlation','shield','enrichment','assignment','action'] as const)('%s 告警源回车输入名称且不拆逗号，不提供候选下拉', scope => {
  const key = ['assignment','action'].includes(scope) ? 'source_names' : 'source_name';
  const onChange = vi.fn();
  render(<MatchRule scope={scope} value={[[{key,operator:'any_of',value:['A']}]]} onChange={onChange} />);
  const input = screen.getByRole('combobox', {name:'alarmCommon.multiValueInput'});
  fireEvent.change(input, {target:{value:'B,生产'}});
  fireEvent.keyDown(input,{key:'Enter',keyCode:13});
  expect(onChange).toHaveBeenLastCalledWith([[{key,operator:'any_of',value:['A','B,生产']}]]);
  expect(document.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)')).toBeNull();
});

it('级别可以一次选择两个枚举值', () => {
  const onChange = vi.fn();
  render(<MatchRule scope="shield" value={[[{key:'level',operator:'any_of',value:['1']}]]} onChange={onChange} />);
  fireEvent.mouseDown(screen.getAllByRole('combobox')[2]);
  fireEvent.click(screen.getByText('预警'));
  expect(onChange).toHaveBeenLastCalledWith([[{key:'level',operator:'any_of',value:['1','2']}]]);
});

it('未填写内容显示输入提示而不是条件失效', () => {
  render(<MatchRule scope="shield" value={[[{key:'description',operator:'contains',value:''}]]} />);
  expect(screen.getByPlaceholderText('common.inputTip')).toBeTruthy();
  expect(screen.queryByText('alarmCommon.invalidRuleCondition')).toBeNull();
});

it('中文组合输入的回车不提前生成标签，确认后去重', () => {
  const onChange = vi.fn();
  render(<MatchRule scope="assignment" value={[[{key:'source_names',operator:'any_of',value:['平台A']}]]} onChange={onChange} />);
  const input=screen.getByRole('combobox',{name:'alarmCommon.multiValueInput'});
  fireEvent.compositionStart(input);
  fireEvent.change(input,{target:{value:'平台B'}});
  fireEvent.keyDown(input,{key:'Enter',keyCode:229,isComposing:true});
  expect(onChange).not.toHaveBeenCalled();
  fireEvent.compositionEnd(input);
  fireEvent.keyDown(input,{key:'Enter',keyCode:13});
  expect(onChange).toHaveBeenLastCalledWith([[{key:'source_names',operator:'any_of',value:['平台A','平台B']}]]);
  fireEvent.change(input,{target:{value:' 平台A '}});
  fireEvent.keyDown(input,{key:'Enter',keyCode:13});
  expect(onChange).toHaveBeenLastCalledWith([[{key:'source_names',operator:'any_of',value:['平台A','平台B']}]]);
});
