import React, { type ComponentProps } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ProgressNode } from './ticket-flow-board';

vi.mock('@xyflow/react', () => ({ Handle: () => null, Position: { Left: 'left', Right: 'right' } }));
vi.mock('./ticket-collaboration', () => ({ formatTicketTime: (value: string) => value }));
afterEach(cleanup);

it('节点保持简洁，聚焦后显示完整参与人和时间', async () => {
  const props = { data: { label: '主管审批', nodeType: 'approval', state: 'done', outcome: 'accepted', assignees: ['张三', '李四'], started_at: '2026-11-12 10:00', finished_at: '2026-11-12 10:05' } } as ComponentProps<typeof ProgressNode>;
  render(<ProgressNode {...props} />);
  expect(screen.getByText('张三')).toBeTruthy();
  expect(screen.getByText('+1')).toBeTruthy();
  expect(screen.queryByText('李四')).toBeNull();
  expect(screen.queryByText(/2026-11-12/)).toBeNull();
  fireEvent.focus(screen.getByLabelText('主管审批，接受'));
  await waitFor(() => expect(screen.getByText('李四')).toBeTruthy());
  expect(screen.getByText('到达时间 2026-11-12 10:00')).toBeTruthy();
  expect(screen.getByText('处理时间 2026-11-12 10:05')).toBeTruthy();
});

it('当前节点有可见定位标识，离开节点后移除', () => {
  const props = { data: { label: '提单', nodeType: 'submit', state: 'current', assignees: ['张三'] } } as ComponentProps<typeof ProgressNode>;
  const { rerender } = render(<ProgressNode {...props} />);
  expect(screen.getByText('当前节点')).toBeTruthy();
  expect(screen.getByLabelText('提单，待处理').getAttribute('aria-current')).toBe('step');
  rerender(<ProgressNode {...props} data={{ ...props.data, state: 'done', outcome: 'passed' }} />);
  expect(screen.queryByText('当前节点')).toBeNull();
});

it('系统执行期间标明实际节点，结果返回后移除旋转标识', () => {
  const props = { data: { label: '发布验收知识', nodeType: 'auto', state: 'current', executing: true, assignees: [] } } as ComponentProps<typeof ProgressNode>;
  const { rerender } = render(<ProgressNode {...props} />);
  expect(screen.getByLabelText('发布验收知识，执行中').getAttribute('aria-current')).toBe('step');
  expect(screen.getByText('执行中')).toBeTruthy();
  rerender(<ProgressNode {...props} data={{ ...props.data, state: 'done', executing: false }} />);
  expect(screen.queryByText('执行中')).toBeNull();
});

it.each(['call', 'subprocess', 'subprocess_submit'])('调用节点 %s 显示正在等待子流程', nodeType => {
  const props = { data: { label: '调用交付子流程', nodeType, state: 'current', executing: true, assignees: [] } } as ComponentProps<typeof ProgressNode>;
  render(<ProgressNode {...props} />);
  expect(screen.getByText('等待子流程办理')).toBeTruthy();
});
