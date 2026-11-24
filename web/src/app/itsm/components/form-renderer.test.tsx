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
