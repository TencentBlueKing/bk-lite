import React from 'react';
import { App } from 'antd';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import TicketDetailPage from './ticket-detail-page';

const api = vi.hoisted(() => ({ ready: true, getTicket: vi.fn(), operateTicket: vi.fn() }));
vi.mock('next/navigation', () => ({ useParams: () => ({ id: '9' }), useRouter: () => ({}) }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../settings/runtime-settings', () => ({ useItsmRuntimeSettings: () => ({ settings: {} }) }));
vi.mock('./ticket-social', () => ({ TicketHeaderSocial: () => null, TicketRelations: () => null }));
vi.mock('./ticket-collaboration', () => ({ TicketCollaboration: () => null, formatTicketTime: () => '' }));
vi.mock('./ticket-flow-board', () => ({ TicketFlowBoard: () => null }));
vi.mock('./ticket-history', () => ({ TicketHistory: () => null }));
vi.mock('./ticket-trigger-records', () => ({ TicketTriggerRecords: () => null }));
vi.mock('./ticket-survey', () => ({ TicketSurveyPanel: () => null }));
vi.mock('./ticket-sla', () => ({ TicketSla: () => null }));
vi.mock('@/app/opspilot/components/ai-editor', () => ({ default: () => null }));
vi.mock('@/components/group-tree-select', () => ({ default: () => null }));
vi.mock('./user-selector', () => ({ UserSelector: () => null }));
vi.mock('./subprocess-field', () => ({ SubProcessField: () => null }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener() {}, removeListener() {} }) });
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const detail = (id: number) => ({
  id: 9, status: 'processing', title: '并行审批', nodes: [], creator: 'tester', selected_task_id: id,
  fields: [{ key: 'node' + id, type: 'input', label: '节点字段' + id, required: true }], form_data: { ['node' + id]: '原值' },
  tasks: [1, 2].map(key => ({ id: key, node_id: 'node' + key, node_name: '处理' + key, can_operate: true, allowed_actions: ['save'] })),
});
it('读取无权工单后可返回或重试，切换并行任务后仅提交对应表单', async () => {
  api.getTicket.mockRejectedValueOnce(Object.assign(new Error('无权访问'), { status: 403 })).mockImplementation(async (_id, taskId) => detail(taskId || 1));
  api.operateTicket.mockResolvedValue({});
  render(<App><TicketDetailPage /></App>);
  await screen.findByText('工单不存在或当前账号没有访问权限');
  expect(screen.getByRole('link', { name: '返回工单列表' }).getAttribute('href')).toBe('/itsm/tickets');
  fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }));
  await screen.findByLabelText('节点字段1');
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '处理任务' }));
  fireEvent.click(screen.getByText('处理2'));
  const field = await screen.findByLabelText('节点字段2');
  expect(screen.queryByLabelText('节点字段1')).toBeNull();
  fireEvent.change(field, { target: { value: '实际处理' } });
  fireEvent.click(screen.getByRole('button', { name: /^保\s*存$/ }));
  await waitFor(() => expect(api.operateTicket).toHaveBeenCalledWith(9, expect.objectContaining({ task_id: 2, form_data: { node2: '实际处理' } })));
});
