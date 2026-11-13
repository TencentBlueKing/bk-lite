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
