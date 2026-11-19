import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
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
