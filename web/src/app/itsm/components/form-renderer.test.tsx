import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FormRenderer } from './form-renderer';

vi.mock('@/app/opspilot/components/ai-editor', () => ({ default: () => null }));
vi.mock('@/components/group-tree-select', () => ({ default: () => null }));
vi.mock('./user-selector', () => ({ UserSelector: () => null }));
vi.mock('./subprocess-field', () => ({ SubProcessField: () => null }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => ({ ready: false }) }));
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
