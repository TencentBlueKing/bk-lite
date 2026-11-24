import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { StrictMode } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import messages from '../../locales/zh.json';
import type { TriggerItem } from './trigger-config';
import { TriggerEditor } from './trigger-editor';

vi.mock('@/app/itsm/components/user-selector', () => ({
  UserSelector: ({ ariaLabel, value, onChange }: { ariaLabel: string; value: string[]; onChange: (users: string[]) => void }) =>
    <input aria-label={ariaLabel} value={value.join(',')} onChange={event => onChange(event.target.value.split(','))} />,
}));

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }),
});

afterEach(cleanup);

const options = {
  workflows: [{ id: 38, name: '采购流程' }],
  forms: [],
  services: [],
  statuses: [{ key: 'new', name: '待处理' }],
  system_fields: [
    { key: '$ticket.title', label: '工单标题', type: 'text' },
    { key: '$ticket.status', label: '工单状态', type: 'text', options: [{ label: '待处理', value: 'new' }] },
  ],
  form_field_groups: [
    { name: '采购流程', workflow_id: 38, fields: [{ key: '$form.amount', label: '申请金额', type: 'number' }] },
    { name: '其他流程', workflow_id: 39, fields: [
      { key: '$form.amount', label: '申请金额', type: 'number' },
      { key: '$form.region', label: '申请地区', type: 'text' },
    ] },
  ],
  notice: {
    groups: [{ id: 8, name: 'IT 支持组' }],
    channels: [{ id: 67, name: '服务台即时消息' }],
    templates: [
      { id: 21, event: 'ticket_end', channel_type: 'im', title_tpl: '完结提醒' },
      { id: 22, event: 'ticket_end', channel_type: 'site', title_tpl: '站内完结提醒' },
    ],
    form_field_groups: [
      { name: '采购流程', workflow_id: 38, fields: [{ key: 'contact', label: '采购联系人' }] },
      { name: '其他流程', workflow_id: 39, fields: [{ key: 'other_contact', label: '其他联系人' }] },
    ],
  },
};

function openEditor(
  onSave = vi.fn().mockResolvedValue(undefined),
  getOptions = vi.fn().mockResolvedValue(options),
  item?: TriggerItem,
) {
  const translations = Object.fromEntries(
    Object.entries(messages.itsm).flatMap(([group, labels]) =>
      Object.entries(labels).filter(([, text]) => typeof text === 'string').map(([key, text]) => [`itsm.${group}.${key}`, text as string])),
  );
  return render(<StrictMode><IntlProvider locale="zh" messages={{ ...translations, 'common.retry': '重试' }}>
    <TriggerEditor item={item} getOptions={getOptions}
      onCancel={vi.fn()} onSave={onSave} />
  </IntlProvider></StrictMode>);
}

async function selectOption(name: string, label: string) {
  const input = screen.getByRole('combobox', { name, exact: true });
  fireEvent.mouseDown(input);
  const option = await waitFor(() => {
    const match = screen.queryAllByText(label, { exact: true }).find(element =>
      element.closest('.ant-select-dropdown:not(.ant-select-dropdown-hidden):not(.ant-slide-up-leave)'),
    );
    if (!match) throw new Error(`未找到选项 ${label}`);
    return match;
  });
  fireEvent.click(option);
}

it('保存组合条件和调整后的动作顺序', async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  openEditor(onSave);
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '工单规则' } });

  fireEvent.click(screen.getByRole('button', { name: '添加条件' }));
  await selectOption('字段 1', '工单标题');
  fireEvent.change(screen.getByLabelText('值 1'), { target: { value: '工单' } });
  fireEvent.click(screen.getByRole('button', { name: '添加条件组' }));
  await selectOption('字段 2.1', '工单状态');
  await selectOption('值 2.1', '待处理');

  fireEvent.change(screen.getByLabelText('标签名称 1'), { target: { value: '原先第一项' } });
  fireEvent.click(screen.getByRole('button', { name: '添加动作' }));
  fireEvent.change(screen.getByLabelText('标签名称 2'), { target: { value: '调整到第一项' } });
  fireEvent.click(screen.getByRole('button', { name: '上移动作 2' }));
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));

  await waitFor(() => expect(onSave).toHaveBeenCalledWith({
    name: '工单规则',
    event: 'ticket_create',
    action: 'tag',
    config: {
      scope: { mode: 'all' },
      when: { logic: 'and', items: [
        { field: '$ticket.title', op: '=', value: '工单' },
        { logic: 'and', items: [{ field: '$ticket.status', op: '=', value: 'new' }] },
      ] },
      actions: [{ type: 'tag', value: '调整到第一项' }, { type: 'tag', value: '原先第一项' }],
    },
  }));
});

it('阻止无效配置保存并在抽屉显示后端拒绝原因', async () => {
  const onSave = vi.fn().mockRejectedValue(new Error('该服务已删除'));
  openEditor(onSave);
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  expect(await screen.findByText('请填写触发器名称')).toBeTruthy();
  expect(onSave).not.toHaveBeenCalled();

  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '工单规则' } });
  fireEvent.change(screen.getByLabelText('标签名称 1'), { target: { value: '测试标签' } });
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  expect(await screen.findByText('该服务已删除')).toBeTruthy();
  expect(screen.getByRole('dialog', { name: '新建触发器' })).toBeTruthy();
});

it('打开抽屉仅查询一次选项，失败后允许重新查询', async () => {
  const getOptions = vi.fn().mockRejectedValueOnce(new Error('网络异常')).mockResolvedValueOnce(options);
  openEditor(undefined, getOptions);
  expect(await screen.findByText('加载范围和状态选项失败')).toBeTruthy();
  expect(getOptions).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }));
  await waitFor(() => expect(screen.queryByText('加载范围和状态选项失败')).toBeNull());
  expect(getOptions).toHaveBeenCalledTimes(2);
});

it.each([
  ['仅在所选范围生效', 'include'],
  ['排除所选范围', 'exclude'],
])('集中配置时可以选择%s并保存所选流程', async (scopeLabel, mode) => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  openEditor(onSave, vi.fn().mockResolvedValue({
    ...options,
    workflows: [{ id: 38, name: '采购流程' }],
  }));
  expect((screen.getByRole('radio', { name: '不限' }) as HTMLInputElement).checked).toBe(true);
  expect(screen.queryByRole('combobox', { name: '流程', exact: true })).toBeNull();
  fireEvent.click(screen.getByRole('radio', { name: scopeLabel }));
  const workflow = screen.getByRole('combobox', { name: '流程', exact: true });
  expect(screen.getByRole('combobox', { name: '表单模型' })).toBeTruthy();
  expect(screen.getByRole('combobox', { name: '服务' })).toBeTruthy();
  await waitFor(() => expect(workflow.getAttribute('disabled')).toBeNull());
  fireEvent.mouseDown(workflow);
  fireEvent.click(await screen.findByText('采购流程'));
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '流程范围' } });
  fireEvent.change(screen.getByLabelText('标签名称 1'), { target: { value: '采购' } });
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() => expect(onSave).toHaveBeenCalledWith({
    name: '流程范围',
    event: 'ticket_create',
    action: 'tag',
    config: { scope: { mode, workflow_ids: [38] }, actions: [{ type: 'tag', value: '采购' }] },
  }));
});


it('按生效范围搜索表单字段并以数值保存条件', async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  openEditor(onSave);
  fireEvent.click(screen.getByRole('radio', { name: '仅在所选范围生效' }));
  await waitFor(() => expect(screen.getByRole('combobox', { name: '流程', exact: true }).getAttribute('disabled')).toBeNull());
  await selectOption('流程', '采购流程');
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '流程条件' } });
  fireEvent.change(screen.getByLabelText('标签名称 1'), { target: { value: '大额采购' } });
  fireEvent.click(screen.getByRole('button', { name: '添加条件' }));

  const fields = screen.getByRole('combobox', { name: '字段 1', exact: true });
  fireEvent.mouseDown(fields);
  expect(await screen.findByText('系统变量')).toBeTruthy();
  expect(screen.getByText('表单字段')).toBeTruthy();
  expect(screen.queryByText('申请地区')).toBeNull();
  fireEvent.change(fields, { target: { value: 'amount' } });
  expect(screen.queryByText('工单标题')).toBeNull();
  fireEvent.click(screen.getByText('申请金额', { exact: true }));
  await selectOption('运算符 1', '大于等于');
  fireEvent.change(screen.getByRole('spinbutton', { name: '值 1' }), { target: { value: '300' } });
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
    config: expect.objectContaining({ when: { logic: 'and', items: [{ field: '$form.amount', op: '>=', value: 300 }] } }),
  })));
});

it('旧条件展示字段名称并保留原有标识，也可显式选择手动输入', async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  openEditor(onSave, vi.fn().mockResolvedValue(options), {
    id: 1, name: '旧规则', event: 'ticket_create', action: 'tag', is_enabled: true,
    config: { when: { field: 'amount', op: '=', value: 300 }, actions: [{ type: 'tag', value: '采购工单' }] },
  });
  expect(await screen.findByText('申请金额', { exact: true })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '添加条件' }));
  await selectOption('字段 2', '手动输入字段');
  fireEvent.change(screen.getByLabelText('字段标识 2'), { target: { value: 'custom.amount' } });
  fireEvent.change(screen.getByLabelText('值 2'), { target: { value: '旧系统' } });
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
    config: expect.objectContaining({ when: { logic: 'and', items: [
      { field: 'amount', op: '=', value: 300 },
      { field: 'custom.amount', op: '=', value: '旧系统' },
    ] } }),
  })));
});

it('通过一个通知人入口组合四类选项，再保存所选渠道和模板', async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  openEditor(onSave);
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '采购通知' } });
  fireEvent.click(screen.getByRole('radio', { name: '仅在所选范围生效' }));
  await waitFor(() => expect(screen.getByRole('combobox', { name: '流程', exact: true }).getAttribute('disabled')).toBeNull());
  await selectOption('流程', '采购流程');
  await selectOption('动作 1', '发送通知');
  const recipients = screen.getByRole('button', { name: '通知人 1', exact: true });
  expect(screen.queryByRole('combobox', { name: '工单角色 1' })).toBeNull();
  expect(screen.queryByRole('combobox', { name: '用户组 1' })).toBeNull();
  fireEvent.click(recipients);
  await selectOption('工单角色 1', '当前处理人');
  fireEvent.click(screen.getByRole('radio', { name: '指定人员', exact: true }));
  expect(screen.queryByRole('combobox', { name: '工单角色 1' })).toBeNull();
  fireEvent.change(screen.getByLabelText('指定人员 1'), { target: { value: 'alice' } });
  fireEvent.click(screen.getByRole('radio', { name: '用户组', exact: true }));
  await selectOption('用户组 1', 'IT 支持组');

  fireEvent.click(screen.getByRole('radio', { name: '表单人员字段', exact: true }));
  const field = screen.getByRole('combobox', { name: '表单人员字段 1' });
  fireEvent.mouseDown(field);
  expect(await screen.findByText(/采购联系人/)).toBeTruthy();
  expect(screen.queryByText(/其他联系人/)).toBeNull();
  fireEvent.click(screen.getByText(/采购联系人/));
  fireEvent.click(recipients);
  const selections = screen.getByRole('list', { name: '已选通知人 1' });
  for (const text of ['提单人', '当前处理人', 'alice', 'IT 支持组', '采购联系人']) {
    expect(within(selections).getByText(text, { exact: true })).toBeTruthy();
  }
  fireEvent.click(within(selections).getByRole('button', { name: '移除alice' }));
  expect(within(selections).queryByText('alice', { exact: true })).toBeNull();
  expect(recipients.getAttribute('aria-expanded')).toBe('false');
  fireEvent.click(recipients);
  fireEvent.click(screen.getByRole('radio', { name: '指定人员', exact: true }));
  fireEvent.change(screen.getByLabelText('指定人员 1'), { target: { value: 'alice' } });
  fireEvent.click(recipients);

  await selectOption('通知渠道 1', '服务台即时消息');
  await selectOption('通知渠道 1', '站内通知');
  const template = screen.getByRole('combobox', { name: '通知模板 1 · 服务台即时消息' });
  fireEvent.mouseDown(template);
  expect(await screen.findByText('完结提醒（ticket_end）')).toBeTruthy();
  expect(screen.queryByText('站内完结提醒（ticket_end）')).toBeNull();
  fireEvent.click(screen.getByText('完结提醒（ticket_end）'));
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));

  await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
    config: { scope: { mode: 'include', workflow_ids: [38] }, actions: [{
      type: 'notice', value: '', notice: {
        content_mode: 'template',
        recipients: { roles: ['creator', 'current_assignees'], users: ['alice'], group_ids: [8], field_keys: ['contact'] },
        channels: [{ type: 'im', channel_id: 67, template_id: 21 }],
      },
    }] },
  })));
});

it('旧通知动作可以继续保存原有投递方式', async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  openEditor(onSave, undefined, {
    id: 2, name: '旧通知规则', event: 'ticket_create', action: 'notice', is_enabled: true,
    config: { actions: [{ type: 'notice', value: '旧通知内容' }] },
  });
  expect(screen.getByRole('button', { name: '配置通知对象和渠道' })).toBeTruthy();
  expect(screen.queryByRole('combobox', { name: '通知渠道 1' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
    config: { scope: { mode: 'all' }, actions: [{ type: 'notice', value: '旧通知内容' }] },
  })));
});

it('通知模板与自定义正文互斥，切换时保留正文草稿', async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  openEditor(onSave);
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '工单提醒' } });
  await selectOption('动作 1', '发送通知');
  expect(screen.queryByRole('textbox', { name: '通知内容 1' })).toBeNull();
  await selectOption('通知模板 1 · 站内通知', '站内完结提醒（ticket_end）');
  fireEvent.click(screen.getByRole('radio', { name: '自定义内容', exact: true }));
  expect(screen.queryByRole('combobox', { name: '通知模板 1 · 站内通知' })).toBeNull();
  fireEvent.change(screen.getByRole('textbox', { name: '通知内容 1' }), { target: { value: '请查看 $ticket_title' } });
  fireEvent.click(screen.getByRole('radio', { name: '选择模板', exact: true }));
  expect(screen.queryByRole('textbox', { name: '通知内容 1' })).toBeNull();
  fireEvent.click(screen.getByRole('radio', { name: '自定义内容', exact: true }));
  expect((screen.getByRole('textbox', { name: '通知内容 1' }) as HTMLTextAreaElement).value).toBe('请查看 $ticket_title');
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
    config: { scope: { mode: 'all' }, actions: [{
      type: 'notice', value: '请查看 $ticket_title', notice: {
        content_mode: 'custom',
        recipients: { roles: ['creator'], users: [], group_ids: [], field_keys: [] },
        channels: [{ type: 'site' }],
      },
    }] },
  })));
});

it('不同流程复用同一人员字段标识时显示两个来源并只保存一个标识', async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  openEditor(onSave, vi.fn().mockResolvedValue({
    ...options,
    notice: {
      ...options.notice,
      form_field_groups: [
        { name: '采购流程', workflow_id: 38, fields: [{ key: 'contact', label: '采购联系人' }] },
        { name: '维护流程', workflow_id: 39, fields: [{ key: 'contact', label: '维护负责人' }] },
      ],
    },
  }));
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '联系相关人员' } });
  await selectOption('动作 1', '发送通知');
  fireEvent.click(screen.getByRole('button', { name: '通知人 1', exact: true }));
  fireEvent.click(screen.getByRole('radio', { name: '表单人员字段', exact: true }));
  const field = screen.getByRole('combobox', { name: '表单人员字段 1' });
  const sharedOption = /采购联系人 · 采购流程.+维护负责人 · 维护流程/;
  fireEvent.mouseDown(field);
  for (const search of ['采购联系人', '维护负责人', 'contact']) {
    fireEvent.change(field, { target: { value: search } });
    expect(await screen.findByText(sharedOption)).toBeTruthy();
  }
  fireEvent.click(screen.getByText(sharedOption));
  expect(screen.getByText('同一字段标识可以用于多个表单，发送时取当前工单的字段值。')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));

  await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
    config: { scope: { mode: 'all' }, actions: [{
      type: 'notice', value: '', notice: {
        content_mode: 'template',
        recipients: { roles: ['creator'], users: [], group_ids: [], field_keys: ['contact'] },
        channels: [{ type: 'site' }],
      },
    }] },
  })));
});
