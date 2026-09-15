import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import MatchRule from '../../(pages)/settings/components/matchRule';

const api = vi.hoisted(() => ({ getAlertSourceOptions: vi.fn() }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/alarm/context/common', () => ({ useCommon: () => ({ levelMeta: {event:{list:[{level_id:1,level_display_name:'严重'},{level_id:2,level_display_name:'预警'}]}} }) }));
vi.mock('@/app/alarm/api/integration', () => ({ useSourceApi: () => api }));
afterEach(cleanup);
beforeAll(() => { window.matchMedia = vi.fn().mockReturnValue({matches:false, addListener:vi.fn(),removeListener:vi.fn()}); });
beforeEach(() => {
  api.getAlertSourceOptions.mockReset().mockResolvedValue([
    { id: 7, name: '平台A', source_id: 'platform-a', source_type: 'restful' },
    { id: 8, name: 'B,生产', source_id: 'platform-b', source_type: 'restful' },
    { id: 9, name: '平台A', source_id: 'platform-a-2', source_type: 'restful' },
  ]);
});

it.each(['correlation','shield','enrichment','assignment','action'] as const)('%s 告警源下拉多选并按名称保存、回显', async scope => {
  const key = ['assignment','action'].includes(scope) ? 'source_names' : 'source_name';
  const onChange = vi.fn();
  const view = render(<MatchRule scope={scope} value={[[{key,operator:'any_of',value:['平台A']}]]} onChange={onChange} />);
  expect(api.getAlertSourceOptions).not.toHaveBeenCalled();
  fireEvent.mouseDown(screen.getByRole('combobox', {name:'alarmCommon.sourceSelect'}));
  fireEvent.click(await screen.findByText('B,生产 (ID: 8)'));
  const saved = [[{key,operator:'any_of',value:['平台A','B,生产']}]];
  expect(onChange).toHaveBeenLastCalledWith(saved);
  expect(screen.getByText('平台A (ID: 7, 9)')).toBeTruthy();
  view.unmount();
  render(<MatchRule scope={scope} value={saved} />);
  expect(Array.from(document.querySelectorAll('.ant-select-selection-item-content')).map(node => node.textContent)).toEqual(['平台A','B,生产']);
});

it.each(['none_of','all_of'] as const)('%s 切换条件保留已选名称，仍使用多选', async operator => {
  const onChange = vi.fn();
  render(<MatchRule scope="assignment" value={[[{key:'source_names',operator:'any_of',value:['平台A']}]]} onChange={onChange} />);
  fireEvent.mouseDown(screen.getAllByRole('combobox')[1]);
  fireEvent.click(screen.getByText(`alarmCommon.multiOperators.${operator}${operator === 'none_of' ? 'List' : ''}`, {selector:'.ant-select-item-option-content'}));
  expect(onChange).toHaveBeenLastCalledWith([[{key:'source_names',operator,value:['平台A']}]])
  fireEvent.mouseDown(screen.getByRole('combobox',{name:'alarmCommon.sourceSelect'}));
  fireEvent.click(await screen.findByText('B,生产 (ID: 8)'));
  expect(onChange).toHaveBeenLastCalledWith([[{key:'source_names',operator,value:['平台A','B,生产']}]]);
});

it.each(['生产', '8', 'platform-b'])('支持搜索名称、ID、接入标识：%s', async search => {
  render(<MatchRule scope="assignment" value={[[{key:'source_names',operator:'any_of',value:[]}]]} />);
  const input = screen.getByRole('combobox',{name:'alarmCommon.sourceSelect'});
  fireEvent.mouseDown(input);
  await screen.findByText('B,生产 (ID: 8)');
  fireEvent.change(input,{target:{value:search}});
  expect(screen.getByText('B,生产 (ID: 8)')).toBeTruthy();
  expect(screen.queryByText('平台A (ID: 7, 9)')).toBeNull();
});

it('不允许输入不存在的告警源；保留旧规则中已删除或改名的值', async () => {
  const onChange = vi.fn();
  render(<MatchRule scope="assignment" value={[[{key:'source_names',operator:'any_of',value:['旧名称']}]]} onChange={onChange} />);
  expect(screen.getByText('旧名称')).toBeTruthy();
  const input = screen.getByRole('combobox',{name:'alarmCommon.sourceSelect'});
  fireEvent.mouseDown(input);
  await screen.findByText('B,生产 (ID: 8)');
  fireEvent.change(input,{target:{value:'不存在的来源'}});
  fireEvent.keyDown(input,{key:'Enter',keyCode:13});
  expect(onChange).not.toHaveBeenCalled();
});

it('加载失败可重试；重复打开不重复请求，也不丢失已选值', async () => {
  api.getAlertSourceOptions.mockRejectedValueOnce(new Error('network'));
  render(<MatchRule scope="assignment" value={[[{key:'source_names',operator:'any_of',value:['平台A']}]]} />);
  const input = screen.getByRole('combobox',{name:'alarmCommon.sourceSelect'});
  fireEvent.mouseDown(input);
  fireEvent.click(await screen.findByText('alarmCommon.sourceOptionsRetry'));
  await screen.findByText('B,生产 (ID: 8)');
  fireEvent.keyDown(input,{key:'Escape',keyCode:27});
  fireEvent.mouseDown(input);
  expect(api.getAlertSourceOptions).toHaveBeenCalledTimes(2);
  expect(screen.getByText('平台A', {selector:'.ant-select-selection-item-content'})).toBeTruthy();
});

it('空列表可以正常加载且不生成自由输入项', async () => {
  api.getAlertSourceOptions.mockResolvedValue([]);
  const onChange = vi.fn();
  render(<MatchRule scope="shield" value={[[{key:'source_name',operator:'any_of',value:[]}]]} onChange={onChange} />);
  const input = screen.getByRole('combobox',{name:'alarmCommon.sourceSelect'});
  fireEvent.mouseDown(input);
  await waitFor(() => expect(document.querySelector('.ant-select-loading')).toBeNull());
  fireEvent.change(input,{target:{value:'新名称'}});
  fireEvent.keyDown(input,{key:'Enter',keyCode:13});
  expect(onChange).not.toHaveBeenCalled();
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
