import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AssignmentModal from '../../(pages)/settings/alertAssign/components/operateModal';
import ShieldModal from '../../(pages)/settings/shieldStrategy/components/operateModal';
import CorrelationModal from '../../(pages)/settings/correlationRules/components/operateModal';
import EnrichmentModal from '../../(pages)/settings/alertEnrichment/components/operateModal';
import ActionModal from '../../(pages)/settings/actionRules/components/operateModal';
import fieldOperatorContract from '../../../../../../specs/changes/alert-rule-types/field-operator-test-matrix.json';

const api = vi.hoisted(() => ({
  getChannelList: vi.fn(), getNotificationTemplateOptions: vi.fn(),
  createAssignment: vi.fn(), updateAssignment: vi.fn(), createShield: vi.fn(), updateShield: vi.fn(),
  getAlertSourceOptions: vi.fn(),
  createCorrelationRule: vi.fn(), updateCorrelationRule: vi.fn(), createEnrichment: vi.fn(), updateEnrichment: vi.fn(),
  createActionRule: vi.fn(), updateActionRule: vi.fn(), getActionJobScripts: vi.fn(), getActionJobScript: vi.fn(),
}));
vi.mock('@/app/alarm/api/settings', () => ({ useSettingApi: () => api }));
vi.mock('@/app/alarm/api/integration', () => ({ useSourceApi: () => api }));
vi.mock('@/context/userInfo', () => ({useUserInfoContext: () => ({selectedGroup:{id:1}})}));
vi.mock('@/components/group-tree-select', () => ({default: () => <span>组织目录</span>}));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => ({
  'alarmCommon.monitorSource': '监控源',
  'alarmCommon.ruleFields.push_source_id': '监控源',
  'alarmCommon.ruleFields.push_source_ids': '监控源',
  'alarmCommon.sourceInputPlaceholder': '输入监控源',
}[key] || key) }) }));
vi.mock('@/app/alarm/context/common', () => ({ useCommon: () => ({
  levelList: [], levelMap: {}, levelMeta: {
    event: { list: [{ level_id: 1, level_display_name: '事件严重' }, { level_id: 2, level_display_name: '事件预警' }] },
    alert: { list: [{ level_id: 1, level_display_name: '告警严重' }, { level_id: 2, level_display_name: '告警预警' }] },
  }, userList: [{ username: 'operator', display_name: '运维' }],
}) }));

beforeEach(() => {
  vi.clearAllMocks();
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false, addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
  });
  api.getChannelList.mockResolvedValue([{ id: 1, name: '邮件', channel_type: 'email' }]);
  api.getNotificationTemplateOptions.mockResolvedValue([]);
  api.getAlertSourceOptions.mockResolvedValue([]);
  api.getActionJobScripts.mockResolvedValue([{id:1,name:'脚本'}]);
  api.getActionJobScript.mockResolvedValue({id:1,params:[]});
  for (const save of [api.createCorrelationRule,api.updateCorrelationRule,api.createEnrichment,api.updateEnrichment,api.createActionRule,api.updateActionRule]) save.mockResolvedValue({});
  for (const save of [api.createAssignment, api.updateAssignment, api.createShield, api.updateShield]) save.mockResolvedValue({});
});
afterEach(cleanup);

const cases = [
  { name: '分派', Component: AssignmentModal, field: 'push_source_ids', create: api.createAssignment, update: api.updateAssignment },
  { name: '屏蔽', Component: ShieldModal, field: 'push_source_id', create: api.createShield, update: api.updateShield },
];
const effectiveTime = { type: 'day', week_month: [], start_time: '00:00:00', end_time: '23:59:59' };
const row = {
  name: '来源策略', match_type: 'filter', match_rules: [[{ key: 'title', operator: 'eq', value: 'CPU' }]],
  personnel: ['operator'], config: effectiveTime, suppression_time: effectiveTime,
  notify_channels: [{ id: 1 }], notification_scenario: [], notification_frequency: {},
};

describe('五个正式配置页面的类型化保存', () => {
  const allCases = [
    ...cases.map(item => ({...item, submit:'settings.assignStrategy.submit', extra:{}})),
    {name:'相关性',Component:CorrelationModal,create:api.createCorrelationRule,update:api.updateCorrelationRule,submit:'common.confirm',extra:{strategy_type:'smart_denoise',team:[1],dispatch_team:[1],params:{window_size:5,group_by:['resource_name']}}},
    {name:'丰富',Component:EnrichmentModal,create:api.createEnrichment,update:api.updateEnrichment,submit:'common.confirm',extra:{provider_type:'cmdb',namespace:'custom',input_binding:{model_id:'resource_type',inst_uuid:'resource_id'},output_projection:[{source:'owner'}]}},
    {name:'处理',Component:ActionModal,create:api.createActionRule,update:api.updateActionRule,submit:'common.confirm',extra:{team:[1],is_active:true,trigger_events:['created'],action_type:'job',action_config:{script_id:1,target_binding:{mode:'from_alert',host_field:'resource_name'},param_bindings:[]}}},
  ];
  const fieldCases = allCases.flatMap(item => {
    const context = ['分派', '处理'].includes(item.name) ? 'alert' : 'event';
    return Object.entries(fieldOperatorContract[context]).flatMap(([key, operators]) =>
      operators.map(operator => ({ ...item, context, key, operator })));
  });
  it.each(fieldCases)('$name / $key / $operator 正式表单回显、编辑、提交及重开保持语义', async ({ Component, update, submit, extra, context, key, operator }) => {
    const multi = ['any_of', 'all_of', 'none_of'].includes(operator);
    const initial = key === 'level' ? ['1'] : multi ? [`${key}:A`] : `${key}:初始正文`;
    const condition = { key, operator, value: initial };
    const props = {
      open: true, currentRow: { ...structuredClone(row), ...extra, id: 42, match_rules: [[condition]] },
      onClose: vi.fn(), onSuccess: vi.fn(),
    };
    const modal = render(React.createElement(Component as React.ComponentType<typeof props>, props));
    let expectedValue: string | string[];
    if (key === 'level') {
      const label = await screen.findByText(context === 'event' ? '事件严重' : '告警严重');
      const input = label.closest('.ant-select')!.querySelector('[role="combobox"]')!;
      fireEvent.mouseDown(input);
      fireEvent.click(await screen.findByText(context === 'event' ? '事件预警' : '告警预警', { selector: '.ant-select-item-option-content' }));
      expectedValue = ['1', '2'];
    } else if (multi) {
      const input = await screen.findByRole('combobox', { name: 'alarmCommon.multiValueInput' });
      fireEvent.change(input, { target: { value: `${key}:B,生产` } });
      fireEvent.keyDown(input, { key: 'Enter', keyCode: 13 });
      expectedValue = [`${key}:A`, `${key}:B,生产`];
    } else {
      expectedValue = `${key}:修改正文`;
      fireEvent.change(await screen.findByDisplayValue(initial as string), { target: { value: expectedValue } });
    }
    fireEvent.click(screen.getByRole('button', { name: submit }));
    await waitFor(() => expect(update).toHaveBeenCalledOnce());
    const saved = update.mock.calls[0][1];
    expect(saved.match_rules).toEqual([[{ key, operator, value: expectedValue }]]);
    expect(api.getAlertSourceOptions).not.toHaveBeenCalled();
    modal.unmount();
    const reopened = { ...props, currentRow: { ...props.currentRow, ...saved, id: 42 } };
    render(React.createElement(Component as React.ComponentType<typeof reopened>, reopened));
    if (key === 'level') {
      expect(await screen.findByText(context === 'event' ? '事件严重' : '告警严重')).toBeTruthy();
      expect(await screen.findByText(context === 'event' ? '事件预警' : '告警预警')).toBeTruthy();
    } else if (multi) {
      expect(await screen.findByText(`${key}:A`)).toBeTruthy();
      expect(await screen.findByText(`${key}:B,生产`)).toBeTruthy();
    } else {
      expect(await screen.findByDisplayValue(expectedValue as string)).toBeTruthy();
    }
    expect(screen.queryByText('alarmCommon.invalidRuleCondition')).toBeNull();
  });
  it.each(allCases.flatMap(item => [false, true].map(edit => ({...item, edit}))))('$name 字符串规则新增/编辑后保持单值提交，编辑=$edit', async ({name,Component,create,update,submit,extra,edit}) => {
    const newEnrichment = name === '丰富' && !edit;
    const condition = {key:'title',operator:'eq',value:'host-a'};
    // 行数据从接口进入 Form，真实编辑器负责修改，mock 仅截获 HTTP 边界。
    const props = {open:true,currentRow:newEnrichment ? undefined : {...structuredClone(row),...extra,...(edit ? {id:42} : {}),match_rules:[[condition]]},onClose:vi.fn(),onSuccess:vi.fn()};
    render(React.createElement(Component as React.ComponentType<typeof props>, props));
    if (newEnrichment) {
      fireEvent.change(await screen.findByLabelText('settings.enrichmentName'), {target:{value:'多值丰富'}});
      fireEvent.click(screen.getByRole('radio', {name:'settings.enrichmentScopeFilter'}));
      fireEvent.mouseDown(screen.getAllByRole('combobox')[2]);
      fireEvent.click(await screen.findByText('alarmCommon.sourceOperators.eq', {selector:'.ant-select-item-option-content'}));
    }
    const input = newEnrichment ? screen.getAllByPlaceholderText('common.inputTip').find(node => !(node as HTMLInputElement).value)! : await screen.findByDisplayValue('host-a');
    fireEvent.change(input,{target:{value:'host-c'}});
    fireEvent.click(screen.getByRole('button',{name:submit}));
    const save = edit ? update : create;
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][edit ? 1 : 0].match_rules).toEqual([[{...condition,value:'host-c'}]]);
    expect(edit ? create : update).not.toHaveBeenCalled();
  });
  it.each(allCases)('$name 拒绝标题的数组条件', async ({Component,update,submit,extra}) => {
    const props = {open:true,currentRow:{...structuredClone(row),...extra,id:42,match_rules:[[{key:'title',operator:'any_of',value:['a']}]]},onClose:vi.fn(),onSuccess:vi.fn()};
    const {container} = render(React.createElement(Component as React.ComponentType<typeof props>, props));
    await screen.findByText('alarmCommon.invalidRuleCondition');
    fireEvent.click(screen.getByRole('button',{name:submit}));
    await waitFor(() => expect((container.ownerDocument.querySelectorAll('.ant-form-item-explain-error')).length).toBeGreaterThan(0));
    expect(update).not.toHaveBeenCalled();
  });
  it.each(allCases.filter(item => ['分派','处理'].includes(item.name)).flatMap(item => [false,true].map(edit=>({...item,edit}))))('$name 列表条件通过正式页面保持数组提交，编辑=$edit', async ({Component,create,update,submit,extra,edit}) => {
    const condition={key:'push_source_ids',operator:'all_of',value:['a','b']};
    const props={open:true,currentRow:{...structuredClone(row),...extra,...(edit?{id:42}:{}),match_rules:[[condition]]},onClose:vi.fn(),onSuccess:vi.fn()};
    render(React.createElement(Component as React.ComponentType<typeof props>,props));
    const input=await screen.findByRole('combobox',{name:'alarmCommon.multiValueInput'});
    fireEvent.change(input,{target:{value:'001'}});fireEvent.keyDown(input,{key:'Enter',keyCode:13});fireEvent.keyUp(input,{key:'Enter',keyCode:13});
    fireEvent.click(screen.getByRole('button',{name:submit}));
    const save=edit?update:create;
    await waitFor(()=>expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][edit?1:0].match_rules).toEqual([[{...condition,value:['a','b','001']}]]);
  });

  it.each(allCases.flatMap(item => [false,true].map(edit=>({...item,edit}))))('$name 告警源多名称新增/编辑提交，编辑=$edit', async ({name,Component,create,update,submit,extra,edit}) => {
    const key=['分派','处理'].includes(name)?'source_names':'source_name';
    const condition={key,operator:'any_of',value:['平台A']};
    const newEnrichment=name==='丰富'&&!edit;
    const props={open:true,currentRow:newEnrichment?undefined:{...structuredClone(row),...extra,...(edit?{id:42}:{}),match_rules:[[condition]]},onClose:vi.fn(),onSuccess:vi.fn()};
    render(React.createElement(Component as React.ComponentType<typeof props>,props));
    if(newEnrichment){
      fireEvent.change(await screen.findByLabelText('settings.enrichmentName'),{target:{value:'来源丰富'}});
      fireEvent.click(screen.getByRole('radio',{name:'settings.enrichmentScopeFilter'}));
      fireEvent.mouseDown(screen.getAllByRole('combobox')[1]);
      fireEvent.click(await screen.findByText('alarmCommon.ruleFields.source_name',{selector:'.ant-select-item-option-content'}));
      fireEvent.mouseDown(screen.getAllByRole('combobox')[2]);
      fireEvent.click(await screen.findByText('alarmCommon.candidateOperators.any_of',{selector:'.ant-select-item-option-content'}));
    }
    const input=await screen.findByRole('combobox',{name:'alarmCommon.multiValueInput'});
    if(newEnrichment){fireEvent.change(input,{target:{value:'平台A'}});fireEvent.keyDown(input,{key:'Enter',keyCode:13});}
    fireEvent.change(input,{target:{value:'平台B,生产'}});fireEvent.keyDown(input,{key:'Enter',keyCode:13});
    fireEvent.click(screen.getByRole('button',{name:submit}));
    const save=edit?update:create;
    await waitFor(()=>expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][edit?1:0].match_rules).toEqual([[{...condition,value:['平台A','平台B,生产']}]]);
    expect(api.getAlertSourceOptions).not.toHaveBeenCalled();
  });

});
