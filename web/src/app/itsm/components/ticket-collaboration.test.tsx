import React from 'react';
import { App } from 'antd';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TicketCollaboration } from './ticket-collaboration';

const api = vi.hoisted(() => ({
  ready: true,
  listComments: vi.fn().mockResolvedValue({ items: [{ id: 1, operator: '提交人', content: '原始问题', created_at: '2026-11-12T08:00:00Z', attachment_ids: [] }] }),
  listAttachments: vi.fn().mockResolvedValue({ items: [{ id: 2, name: '说明.txt', size: 42, operator: '其他用户', created_at: '2026-11-12T08:00:00Z', can_delete: false }] }),
  addComment: vi.fn().mockResolvedValue({ id: 3 }),
}));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => api }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: vi.fn().mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() })) });
afterEach(cleanup);

describe('工单评论与附件', () => {
  it('回复保留父评论并提交用户输入', async () => {
    render(<App><TicketCollaboration ticketId={1} /></App>);
    await screen.findByText('原始问题');
    fireEvent.click(screen.getByRole('button', { name: /回\s*复/ }));
    fireEvent.change(screen.getByLabelText('评论内容'), { target: { value: '补充说明' } });
    fireEvent.click(screen.getByRole('button', { name: '发表评论' }));
    await waitFor(() => expect(api.addComment).toHaveBeenCalledWith(1, '补充说明', 1, []));
  });
  it('附件显示上传人和下载入口，其他用户没有删除按钮', async () => {
    render(<App><TicketCollaboration ticketId={1} /></App>);
    await screen.findByText('原始问题');
    fireEvent.click(screen.getByRole('tab', { name: '附件 (1)' }));
    expect(await screen.findByText('说明.txt')).toBeTruthy();
    expect(screen.getByRole('button', { name: /下\s*载/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /删\s*除/ })).toBeNull();
  });
});
