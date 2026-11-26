import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { TicketHistory } from './ticket-history';
import type { TicketHistoryItem, TicketProgressNode } from '../types';

vi.mock('./ticket-collaboration', () => ({ formatTicketTime: (value: string) => value }));
afterEach(cleanup);

it('日志按关联节点展示类型图标，保留用户标签和待处理状态', () => {
  const items = [{ id: '1', node_id: 'approval', name: '主管审批', operator: '张三', state: 'current', started_at: '2026-11-12 10:00', finished_at: '' }] as TicketHistoryItem[];
  const nodes = [{ id: 'approval', type: 'approval' }] as TicketProgressNode[];
  render(<TicketHistory items={items} nodes={nodes} />);
  expect(screen.getByLabelText('审批节点')).toBeTruthy();
  expect(screen.getByText('张三').closest('.ant-tag')).toBeTruthy();
  expect(screen.getByText('待处理')).toBeTruthy();
  expect(screen.getByText('2026-11-12 10:00')).toBeTruthy();
});

it('回退日志标出实际回退节点和处理意见', () => {
  render(<TicketHistory nodes={[]} items={[{
    id: 'return-1', node_id: 'approval', name: '主管审批', operator: '张三', state: 'done',
    action: 'return', action_label: '回退至 提单', started_at: '', finished_at: '2026-11-19 10:00', message: '',
    opinion: '补充申请材料',
  }]} />);
  expect(screen.getByText('回退至 提单').closest('.ant-tag')).toBeTruthy();
  expect(screen.getByText('补充申请材料')).toBeTruthy();
});

it('流转日志显示人工处理意见，系统提示和其他操作名称保持隐藏', () => {
  const base = {
    node_id: 'approval', name: '主管审批', operator: '张三', state: 'done',
    action: 'approve', action_label: '同意', started_at: '', finished_at: '2026-11-19 10:00', message: '',
  };
  render(<TicketHistory nodes={[]} items={[
    { ...base, id: 'approve-1', opinion: '已核实预算' },
    { ...base, id: 'create-1', action: 'create', action_label: '新建', message: '创建工单' },
  ]} />);
  expect(screen.getByText('已核实预算')).toBeTruthy();
  expect(screen.queryByText('创建工单')).toBeNull();
  expect(screen.queryByText('同意')).toBeNull();
});

it('核对动作必须选择下游结果、说明依据，成功后才推进', async () => {
  const reconcile = vi.fn().mockResolvedValue(undefined);
  const item = {
    id: 'auto-9', node_id: 'api', name: '开通权限', action: 'auto', operator: '系统', state: 'failed',
    action_label: '待核对', message: '结果待核对', started_at: '', finished_at: '', execution_id: 9,
    review_token: 'attempt-token', result_field: 'external_id', job_id: 'job-7',
  };
  const { rerender } = render(<TicketHistory nodes={[]} items={[{ ...item, review_token: undefined }]} reconcile={reconcile} />);
  expect(screen.queryByText('核对执行结果')).toBeNull();
  rerender(<TicketHistory nodes={[]} items={[item]} reconcile={reconcile} />);
  fireEvent.click(screen.getByText('核对执行结果'));
  fireEvent.click(await screen.findByLabelText('已执行成功，仅推进流程'));
  fireEvent.change(screen.getByLabelText('核对依据'), { target: { value: '下游流水 42 已成功' } });
  fireEvent.change(screen.getByLabelText('已核实的返回值'), { target: { value: '"42"' } });
  fireEvent.click(screen.getByRole('button', { name: '确认核对' }));
  await waitFor(() => expect(reconcile).toHaveBeenCalledWith(9, {
    review_token: 'attempt-token', outcome: 'executed', note: '下游流水 42 已成功', result_value: '42',
  }));
});

it('逐行打开对应的作业平台执行记录', () => {
  render(<TicketHistory nodes={[]} items={[{
    id: 'auto-1', node_id: 'job', name: '只读检查', operator: '系统', state: 'done',
    action_label: '自动处理', started_at: '', finished_at: '', message: '',
    job_records: [{ row: 1, job_id: 41 }, { row: 2, job_id: 67 }],
  }]} />);
  expect(screen.getByRole('link', { name: '第 1 行 · 作业 #41' }).getAttribute('href')).toBe('/job/execution/job-record?id=41');
  expect(screen.getByRole('link', { name: '第 2 行 · 作业 #67' }).getAttribute('href')).toBe('/job/execution/job-record?id=67');
});
