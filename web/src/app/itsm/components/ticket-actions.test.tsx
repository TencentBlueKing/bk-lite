import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TicketActions } from './ticket-actions';
import type { TicketDetail } from '../types';

vi.mock('./user-selector', () => ({ UserSelector: () => null }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: vi.fn().mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() })) });
afterEach(cleanup);
const ticket = { id: 1, tasks: [{ id: 2, node_id: 'approval', node_name: '主管审批', assignee: 'tester', status: 'pending', can_operate: true, allowed_actions: ['approve'] }], allowed_actions: [] } as unknown as TicketDetail;

describe('工单操作权限与确认', () => {
  it('只显示服务端许可的节点按钮', () => {
    render(<TicketActions ticket={ticket} busy={false} operate={vi.fn()} />);
    expect(screen.getByRole('button', { name: /同\s*意/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /驳\s*回/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /回\s*退/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /撤\s*回/ })).toBeNull();
  });
  it('只读用户不展示处理操作', () => {
    render(<TicketActions ticket={{ ...ticket, tasks: ticket.tasks.map((task) => ({ ...task, can_operate: false })) }} busy={false} operate={vi.fn()} />);
    expect(screen.queryByRole('button')).toBeNull();
  });
  it('确认时提交真实意见及对应任务', async () => {
    const operate = vi.fn().mockResolvedValue(true);
    render(<TicketActions ticket={ticket} busy={false} operate={operate} />);
    fireEvent.click(screen.getByRole('button', { name: /同\s*意/ }));
    expect(operate).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('处理意见'), { target: { value: '核验通过' } });
    fireEvent.click(screen.getByRole('button', { name: /确\s*认/ }));
    await waitFor(() => expect(operate).toHaveBeenCalledWith('approve', ticket.tasks[0], expect.objectContaining({ opinion: '核验通过' })));
  });
});
