import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TicketActions } from './ticket-actions';
import type { TicketDetail } from '../types';

vi.mock('./user-selector', () => ({
  UserSelector: ({ onChange, transfer }: {
    onChange: (users: string[]) => void;
    transfer?: { ticketId: number; taskId: number };
  }) => (
    <button onClick={() => onChange(['bob'])}>{`选择接收人 ${transfer?.ticketId}/${transfer?.taskId}`}</button>
  ),
}));
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
  it('按打开时的任务选择接收人，权限刷新后禁止确认', async () => {
    const operate = vi.fn().mockResolvedValue(true);
    const record = {
      ...ticket,
      tasks: [
        { ...ticket.tasks[0], allowed_actions: ['transfer'] },
        { ...ticket.tasks[0], id: 3, node_id: 'handle', node_name: '服务处理', allowed_actions: ['transfer'] },
      ],
    };
    const { rerender } = render(<TicketActions ticket={record} busy={false} operate={operate} />);
    fireEvent.mouseDown(screen.getByRole('combobox', { name: '处理任务' }));
    fireEvent.click(screen.getByText('服务处理'));
    fireEvent.mouseEnter(screen.getByRole('button', { name: '更多操作' }));
    fireEvent.click(await screen.findByRole('menuitem', { name: '转交' }));
    const confirm = await screen.findByRole('button', { name: '确认转交' });
    expect(confirm).toHaveProperty('disabled', true);
    fireEvent.click(await screen.findByRole('button', { name: '选择接收人 1/3' }));
    expect(confirm).toHaveProperty('disabled', false);
    rerender(<TicketActions ticket={{ ...record, tasks: record.tasks.slice(0, 1) }} busy={false} operate={operate} />);
    expect(confirm).toHaveProperty('disabled', true);
    fireEvent.click(confirm);
    expect(operate).not.toHaveBeenCalled();
  });
});

it('节点必填意见为空或全空白时不得提交，即点保存也需确认', async () => {
  const operate = vi.fn().mockResolvedValue(true);
  const task = { ...ticket.tasks[0], allowed_actions: ['save'], required_opinion_actions: ['save'] };
  render(<TicketActions ticket={{ ...ticket, tasks: [task] }} busy={false} operate={operate} />);
  fireEvent.click(screen.getByRole('button', { name: /^保\s*存$/ }));
  const confirm = await screen.findByRole('button', { name: /确认保\s*存/ });
  const input = screen.getByLabelText('处理意见');
  expect(confirm).toHaveProperty('disabled', true);
  fireEvent.change(input, { target: { value: '  \n  ' } });
  fireEvent.click(confirm);
  expect(operate).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: '  保存原因  ' } });
  fireEvent.click(confirm);
  await waitFor(() => expect(operate).toHaveBeenCalledWith('save', task, expect.objectContaining({ opinion: '保存原因' })));
});

it('回退选择已有完成记录的节点，权限刷新后不再允许确认', async () => {
  const operate = vi.fn().mockResolvedValue(true);
  const task = {
    ...ticket.tasks[0],
    allowed_actions: ['return'],
    required_opinion_actions: ['return'],
    return_targets: [{ node_id: 'submit', name: '提单', completed_at: '2026-11-19T01:00:00Z' }],
  };
  const record = { ...ticket, tasks: [task] };
  const { rerender } = render(<TicketActions ticket={record} busy={false} operate={operate} />);
  fireEvent.click(screen.getByRole('button', { name: /^回\s*退$/ }));
  const button = await screen.findByRole('button', { name: /确认回\s*退/ });
  fireEvent.change(screen.getByLabelText('处理意见'), { target: { value: '需补充内容' } });
  expect(button).toHaveProperty('disabled', true);
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '回退节点' }));
  fireEvent.click(await screen.findByText('提单', { selector: '.ant-select-item-option-content span' }));
  expect(button).toHaveProperty('disabled', false);
  rerender(<TicketActions ticket={{ ...record, tasks: [{ ...task, can_operate: false }] }} busy={false} operate={operate} />);
  expect(button).toHaveProperty('disabled', true);
  fireEvent.click(button);
  expect(operate).not.toHaveBeenCalled();
  rerender(<TicketActions ticket={record} busy={false} operate={operate} />);
  fireEvent.click(button);
  await waitFor(() => expect(operate).toHaveBeenCalledWith('return', task, {
    opinion: '需补充内容',
    return_node_id: 'submit',
  }));
});
