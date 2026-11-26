import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FormRenderer } from './form-renderer';

vi.mock('@/app/opspilot/components/ai-editor', () => ({ default: () => null }));
vi.mock('@/components/group-tree-select', () => ({ default: () => null }));
vi.mock('./user-selector', () => ({ UserSelector: () => null }));
vi.mock('./subprocess-field', () => ({ SubProcessField: () => null }));
const mockPresign = vi.hoisted(() => vi.fn());
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => ({ ready: false, presignAttachment: mockPresign }) }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: vi.fn().mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() })) });

describe('嵌套表单渲染', () => {
  it('标签页中的分组字段参与同一表单提交', async () => {
    const submit = vi.fn();
    render(<FormRenderer schema={{ version: 1, fields: [{ key: 'tab', type: 'tab', label: '申请', children: [{ key: 'group', type: 'section', label: '明细', children: [{ key: 'title', type: 'input', label: '标题', required: true }] }] }] }} onSubmit={submit} />);
    fireEvent.change(screen.getByLabelText('标题'), { target: { value: '嵌套申请' } });
    fireEvent.click(screen.getByRole('button', { name: /提\s*交/ }));
    await waitFor(() => expect(submit).toHaveBeenCalledWith({ title: '嵌套申请' }));
  });
  it('父分组只读权限覆盖子字段编辑权限', () => {
    render(<FormRenderer schema={{ version: 1, fields: [{ key: 'group', type: 'section', label: '明细', children: [{ key: 'title', type: 'input', label: '标题' }] }] }} fieldPerm={{ group: 'read', title: 'edit' }} initialValues={{ title: '原值' }} onSubmit={() => undefined} />);
    expect((screen.getByLabelText('标题') as HTMLInputElement).disabled).toBe(true);
  });
});

it('已有工单的附件上传使用所选节点和字段的授权上下文', async () => {
  const signed = { url: '/signed-upload', object_name: 'example.txt' };
  mockPresign.mockResolvedValue(signed);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }));
  try {
    const { container } = render(<FormRenderer schema={{ version: 1, fields: [{ key: 'files', type: 'attachment', label: '节点附件' }] }}
      fetchContext={{ ticket_id: 91, task_id: 12 }} onSubmit={vi.fn()} />);
    fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [new File(['样例'], 'test.txt')] } });
    await waitFor(() => expect(mockPresign).toHaveBeenCalledWith('test.txt', 91, { task_id: 12, field: 'files' }));
  } finally { vi.unstubAllGlobals(); }
});

it('分组可见条件与条件必填随输入即时生效', async () => {
  const submit = vi.fn();
  render(<FormRenderer schema={{ version: 1, fields: [
    { key: 'kind', type: 'input', label: '申请类别' },
    { key: 'group', type: 'section', label: '附加信息', visibleWhen: { field: 'kind', op: '=', value: 'show' },
      children: [{ key: 'notes', type: 'input', label: '处理备注' }] },
  ], rules: [{ field: 'notes', type: 'required', when: { field: 'kind', op: 'not_empty' } }] }} onSubmit={submit} />);
  expect(screen.queryByLabelText('处理备注')).toBeNull();
  fireEvent.change(screen.getByLabelText('申请类别'), { target: { value: 'show' } });
  fireEvent.click(screen.getByRole('button', { name: /提\s*交/ }));
  await waitFor(() => expect(screen.getByLabelText('处理备注').getAttribute('aria-invalid')).toBe('true'));
  expect(submit).not.toHaveBeenCalled();
});

const machineSchema = { version: 1, fields: [{ key: 'machines', type: 'table', label: '虚拟机', required: true, children: [
  {key:'name', label:'主机名', type:'input', required:true}, {key:'owner', label:'负责人', type:'input', required:true},
] }] };

it.each([undefined, {machines: []}])('新建或空草稿默认有一行，部分填写时不报错，提交时校验缺失的列', async initialValues => {
  const submit = vi.fn();
  render(<FormRenderer schema={machineSchema} initialValues={initialValues} onSubmit={submit} />);
  const name = screen.getByLabelText('主机名 1');
  fireEvent.change(name, {target: {value:'vm-01'}});
  await new Promise(resolve => setTimeout(resolve, 50));
  expect(screen.queryByText(/请填写第 1 行/)).toBeNull();
  fireEvent.click(screen.getByRole('button', {name:/提\s*交/}));
  expect(await screen.findByText(/请填写第 1 行的负责人/)).toBeTruthy();
  expect(submit).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('负责人 1'), {target:{value:'运维'}});
  fireEvent.click(screen.getByRole('button', {name:/提\s*交/}));
  await waitFor(() => expect(submit).toHaveBeenCalledWith({machines:[{name:'vm-01',owner:'运维'}]}));
});

it('保留已保存草稿中的行，只读空表保留空态', () => {
  const { unmount } = render(<FormRenderer schema={machineSchema} initialValues={{machines:[{name:'vm-01'}, {name:'vm-02'}]}} onSubmit={vi.fn()} />);
  expect(screen.getByDisplayValue('vm-02')).toBeTruthy();
  expect(screen.queryByLabelText('主机名 3')).toBeNull();
  unmount();
  render(<FormRenderer schema={machineSchema} initialValues={{machines:[]}} readOnly onSubmit={vi.fn()} />);
  expect(screen.getByText('暂无数据')).toBeTruthy();
});

it('可选表格的空白首行允许提交', async () => {
  const submit = vi.fn();
  render(<FormRenderer schema={{ ...machineSchema, fields: [{ ...machineSchema.fields[0], required: false }] }} onSubmit={submit} />);
  fireEvent.click(screen.getByRole('button', {name:/提\s*交/}));
  await waitFor(() => expect(submit).toHaveBeenCalledOnce());
  expect(screen.queryByText(/请填写第 1 行/)).toBeNull();
});

it('子表单的复选和多行文本按行编辑并提交原生值', async () => {
  const submit = vi.fn();
  const fields = [{ key: 'items', type: 'table', label: '明细', children: [
    { type: 'checkbox', key: 'systems', label: '系统', required: true, source: { type: 'static', options: [{ label: 'Linux', value: 'linux' }] } },
    { type: 'textarea', key: 'notes', label: '说明', rows: 4 },
    { type: 'time', key: 'start', label: '开始时间' },
  ] }];
  render(<FormRenderer schema={{ version: 1, fields }} initialValues={{ items: [{ start: '09:25:31' }] }} onSubmit={submit} />);
  fireEvent.click(screen.getByRole('checkbox', { name: 'Linux' }));
  const notes = screen.getByLabelText('说明 1');
  expect(notes.tagName).toBe('TEXTAREA');
  fireEvent.change(notes, { target: { value: '两行\n说明' } });
  expect(screen.getByDisplayValue('09:25:31')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '复制行' }));
  const boxes = screen.getAllByRole('checkbox', { name: 'Linux' });
  fireEvent.click(boxes[1]);
  fireEvent.click(screen.getByRole('button', { name: /提\s*交/ }));
  await screen.findByText('请填写第 2 行的系统');
  fireEvent.click(boxes[1]);
  fireEvent.click(screen.getByRole('button', { name: /提\s*交/ }));
  const row = { start: '09:25:31', systems: ['linux'], notes: '两行\n说明' };
  await waitFor(() => expect(submit).toHaveBeenCalledWith({ items: [row, row] }));
});

it.each([
  { anyLevel: true, path: false, choice: '华东', expected: 'east', display: '华东' },
  { anyLevel: false, path: true, choice: '上海', expected: 'sh', display: '华东 / 上海' },
])('子表单级联按层级和路径配置选择并提交 $display', async ({ anyLevel, path, choice, expected, display }) => {
  const submit = vi.fn();
  const location = { key: 'city', type: 'cascade', label: '地点', cascadeAnyLevel: anyLevel, showCascadePath: path,
    source: { type: 'static', options: [{ label: '华东', value: 'east', children: [{ label: '上海', value: 'sh' }] }] } };
  render(<FormRenderer schema={{ version: 1, fields: [{ key: 'lines', type: 'table', label: '明细', children: [location] }] }} onSubmit={submit} />);
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '地点 1' }));
  const parent = await screen.findByText('华东');
  if (!anyLevel) {
    fireEvent.click(parent);
    expect(screen.getByRole('combobox', { name: '地点 1' }).getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(parent.closest('[role="treeitem"]')!.querySelector('.ant-select-tree-switcher')!);
  }
  fireEvent.click(await screen.findByText(choice));
  expect(screen.getByRole('table').querySelector('[title="' + display + '"]')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /提\s*交/ }));
  await waitFor(() => expect(submit).toHaveBeenCalledWith({ lines: [{ city: expected }] }));
});

it('子控件按本行显隐并继承节点的读写权限', async () => {
  const submit = vi.fn();
  const fields = [{ key: 'rows', label: '明细', type: 'table', children: [
    { key: 'kind', type: 'input', label: '类型' }, { key: 'owner', type: 'input', label: '记录人' },
    { key: 'secret', type: 'textarea', label: '内部详情' },
    { key: 'reason', type: 'textarea', label: '原因', required: true, visibleWhen: { field: 'kind', op: '=' as const, value: '其他' } },
  ] }];
  const rows = [{ kind: '常规', owner: '系统', _itsm_row_ref: 'proof1' }, { kind: '其他', owner: '系统', _itsm_row_ref: 'proof2' }];
  render(<FormRenderer schema={{ version: 1, fields }} fieldPerm={{ owner: 'readonly', secret: 'hidden' }} initialValues={{ rows }} onSubmit={submit} />);
  expect(screen.getByRole('textbox', { name: '记录人 2' }).hasAttribute('disabled')).toBe(true);
  expect(screen.queryByText('内部详情')).toBeNull();
  expect(screen.queryByRole('textbox', { name: '原因 1' })).toBeNull();
  fireEvent.change(screen.getByRole('textbox', { name: '原因 2' }), { target: { value: '信息变更' } });
  fireEvent.click(screen.getByRole('button', { name: /提\s*交/ }));
  await waitFor(() => expect(submit).toHaveBeenCalledWith({ rows: [rows[0], { ...rows[1], reason: '信息变更' }] }));
});

it('错误原因定位到缺失的单元格，旁边已填列不会继承红框', async () => {
  render(<FormRenderer schema={machineSchema} initialValues={{machines:[{name:'第一台'},{name:'第二台',owner:'admin'}]}} onSubmit={vi.fn()} />);
  fireEvent.click(screen.getByRole('button',{name:/提\s*交/}));
  const missing=screen.getByLabelText('负责人 1').closest('td')!;
  await waitFor(()=>expect(missing.textContent).toContain('请填写负责人'));
  expect(screen.getByLabelText('负责人 2').className).not.toContain('status-error');
  fireEvent.change(screen.getByLabelText('负责人 1'), {target:{value:'admin'}});
  await waitFor(()=>expect(screen.queryByText(/请填写第 1 行/)).toBeNull());

});

it('只读动态多选按行展示持久化名称', () => {
  render(<FormRenderer readOnly schema={{version:1,fields:[{key:'rows',type:'table',label:'明细',children:[{
    key:'choice',type:'multiselect',label:'规格',fetch:{source:'integration',mode:'options',integration_id:1}
  }]}]}} initialValues={{rows:['华北','华东'].map(label=>({choice:['vm'],_field_labels:{choice:[{label,value:'vm'}]}}))}} onSubmit={vi.fn()} />);
  expect(screen.getByText('华北')).toBeTruthy();
  expect(screen.getByText('华东')).toBeTruthy();
});
