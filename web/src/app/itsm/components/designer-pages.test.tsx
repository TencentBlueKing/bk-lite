import React from 'react';
import { cleanup, render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FormPage from '../form/designer/[id]/page';
import WorkflowPage from '../workflow/designer/[id]/page';
import type { FormFieldSchema, FormSchema } from '../types';

const state = vi.hoisted(() => ({ id: '1' }));
const api = vi.hoisted(() => ({ ready: true, getForm: vi.fn(), getDesign: vi.fn(), saveDesign: vi.fn(), saveForm: vi.fn(), publishForm: vi.fn() }));
vi.mock('next/navigation', () => ({ useParams: () => ({ id: state.id }), useRouter: () => ({}) }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('./interaction-surfaces', () => ({ ItsmDrawer: () => null, ItsmModal: () => null, usePageLeave: () => {} }));
vi.mock('./flow-designer', () => ({ FlowDesigner: () => null }));
vi.mock('./workflow-preview', () => ({ WorkflowPreview: () => null }));
vi.mock('./form-renderer', () => ({
  FormRenderer: ({ fetchContext }: { fetchContext?: { preview?: boolean; schema?: FormSchema } }) =>
    <output>{fetchContext?.preview && fetchContext.schema?.fields.map(field => field.label).join('、')}</output>,
}));
vi.mock('./node-settings', () => ({ flattenNodeFields: () => [] }));
vi.mock('./form-designer', () => ({
  FormDesigner: ({ fields, onChange }: { fields: FormFieldSchema[]; onChange: (value: FormFieldSchema[]) => void }) =>
    <button onClick={() => onChange(fields.map(f => ({ ...f, label: '变更' })))}>{fields[0]?.label}</button>,
}));
const schema = { version: 1, fields: [{ key: 'cost', type: 'number', label: '原名' }], layout: [{ field: 'cost' }], rules: [{ type: 'compute', field: 'cost', expr: 'sum(items)' }] };
beforeEach(() => { vi.resetAllMocks(); state.id = '1'; });
afterEach(cleanup);
it('表单编辑加载失败可重试，保存与发布保留布局和规则', async () => {
  api.getForm.mockRejectedValueOnce(new Error('读取失败')).mockResolvedValue({ schema, versions: [], can_publish: true });
  api.saveForm.mockResolvedValue({ version_no: 3 });
  api.publishForm.mockResolvedValue({ version_no: 4 });
  render(<FormPage />);
  expect(screen.queryByText('itsm.design.saveDraft')).toBeNull();
  await screen.findByText('读取失败');
  fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }));
  fireEvent.click(await screen.findByRole('button', { name: '原名' }));
  fireEvent.click(screen.getByText('itsm.design.saveDraft'));
  const expected = { ...schema, fields: [{ ...schema.fields[0], label: '变更' }] };
  await waitFor(() => expect(api.saveForm).toHaveBeenCalledWith(1, expected));
  fireEvent.click(await screen.findByRole('button', { name: '原名' }));
  fireEvent.click(screen.getByText('itsm.design.publishVersion'));
  await waitFor(() => expect(api.publishForm).toHaveBeenCalledWith(1, expected));
});
it('切换流程后等待对应表单读完，旧请求迟到不会覆盖当前设计', async () => {
  let finish: (value: unknown) => void;
  api.getDesign.mockResolvedValueOnce({ workflow_name: '旧流程', form_id: 1 }).mockResolvedValueOnce({ workflow_name: '新流程', form_id: 2 });
  api.getForm.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValueOnce({ schema });
  const view = render(<WorkflowPage />);
  await waitFor(() => expect(api.getForm).toHaveBeenCalledWith(1));
  expect(screen.queryByText('itsm.common.save')).toBeNull();
  state.id = '2';
  view.rerender(<WorkflowPage />);
  await screen.findByText('新流程');
  await act(async () => finish({ schema: { fields: [] } }));
  expect(screen.queryByText('旧流程')).toBeNull();
  expect(screen.getByRole('button', { name: '原名' })).toBeTruthy();
});

it('预览使用编辑中的表单配置取数', async () => {
  api.getForm.mockResolvedValue({ schema, versions: [], can_publish: false });
  render(<FormPage />);
  fireEvent.click(await screen.findByRole('button', { name: '原名' }));
  expect(screen.queryByText('itsm.design.publishVersion')).toBeNull();
  fireEvent.click(screen.getByText('itsm.design.previewForm'));
  expect(screen.getByRole('status').textContent).toBe('变更');
});

it('从发布版本新建草稿后继续显示版本快照中的字段', async () => {
  const published = { workflow_name: '虚拟机申请', form_id: 8, locked: true, version_no: 4, form_schema: schema };
  api.getDesign.mockResolvedValueOnce(published).mockResolvedValue({ ...published, locked: false, version_no: 5 });
  api.getForm.mockResolvedValue({ schema: { version: 1, fields: [] } });
  render(<WorkflowPage />);
  fireEvent.click(await screen.findByRole('button', { name: '新建草稿' }));
  await waitFor(() => expect(api.saveDesign).toHaveBeenCalledWith(1, { draft_from_version: 4 }));
  await screen.findByText('V5');
  expect(screen.getByRole('button', { name: '原名' })).toBeTruthy();
  expect(api.getForm).not.toHaveBeenCalled();
});
