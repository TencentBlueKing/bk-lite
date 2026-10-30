import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import ItsmTicket from '..';

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/utils/request', () => ({ default: () => http }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', { writable: true, value: vi.fn().mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() })) });
});
afterEach(() => { cleanup(); http.get.mockReset(); http.post.mockReset(); });

describe('ITSM 关联展示', () => {
  it('待确认不提供补建按钮，只提供核查', async () => {
    http.get.mockResolvedValue({ execution_id: 1, execution_status: 'unknown', allowed_actions: ['reconcile'], ticket_id: null });
    render(<ItsmTicket alertId="A1" alertStatus="processing" />);
    expect(await screen.findByText('itsm.unknown')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'itsm.retry' })).toBeNull();
    expect(screen.getByRole('button', { name: 'itsm.reconcile' })).toBeTruthy();
    expect(http.post).not.toHaveBeenCalled();
  });
  it('显示字符串工单编号，保留同步错误且不生成跳转链接', async () => {
    http.get.mockResolvedValue({ ticket_id: '102026090716182700005102', ticket_number: 'DE123', ticket_title: 'CPU', status_label: '处理中', sync_error: '认证失败', allowed_actions: [] });
    render(<ItsmTicket alertId="A1" alertStatus="auto_recovery" />);
    expect(await screen.findByText('102026090716182700005102')).toBeTruthy();
    expect(screen.getByText('认证失败')).toBeTruthy();
    expect(screen.queryByRole('link')).toBeNull();
  });
  it('补建请求失败后重试复用幂等键，成功后刷新关联', async () => {
    http.get.mockResolvedValue({ rule_id: 2, workflow_key: 'flow', execution_status: 'failed', allowed_actions: ['retry'] });
    http.post.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce({ execution_id: 3 });
    render(<ItsmTicket alertId="A1" alertStatus="auto_recovery" />);
    fireEvent.click(await screen.findByRole('button', { name: 'itsm.retry' }));
    expect(await screen.findByText('itsm.endedHint')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /common.confirm$/ }));
    expect(await screen.findByText('itsm.submitFailed')).toBeTruthy();
    const key = http.post.mock.calls[0][2].headers['Idempotency-Key'];
    fireEvent.click(await screen.findByRole('button', { name: /common.confirm$/ }));
    await waitFor(() => expect(http.get).toHaveBeenCalledTimes(2));
    expect(http.post.mock.calls[1][2].headers['Idempotency-Key']).toBe(key);
    expect(http.post.mock.calls[1][1]).toEqual({ alert_id: 'A1', rule_id: 2 });
  });
  it('核查先查询预览，填写依据后才能补录绑定', async () => {
    http.get.mockResolvedValue({ execution_id: 1, execution_status: 'unknown', allowed_actions: ['reconcile'] });
    http.post.mockResolvedValueOnce({ preview: { ticket_id: '123', ticket_title: 'CPU', ticket_number: 'DE123', status_label: '处理中' } }).mockResolvedValueOnce({});
    render(<ItsmTicket alertId="A1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'itsm.reconcile' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'itsm.ticketId' }), { target: { value: '123' } });
    fireEvent.click(screen.getByRole('button', { name: 'itsm.lookup' }));
    expect(await screen.findByText('CPU')).toBeTruthy();
    expect(http.post.mock.calls[0][1].confirm).toBe(false);
    expect(screen.getByRole('button', { name: /common.confirm$/ }).hasAttribute('disabled')).toBe(true);
    fireEvent.change(screen.getByRole('textbox', { name: 'itsm.evidence' }), { target: { value: '核对告警编号和创建时间' } });
    fireEvent.click(screen.getByRole('button', { name: /common.confirm$/ }));
    await waitFor(() => expect(http.get).toHaveBeenCalledTimes(2));
    expect(http.post.mock.calls[1][1]).toEqual({ alert_id: 'A1', execution_id: 1, ticket_id: '123', evidence: '核对告警编号和创建时间', confirm: true });
  });
  it('留言失败可重发，不调用建单接口', async () => {
    http.get.mockResolvedValue({ ticket_id: '123', comment_error: '留言失败', allowed_actions: ['recomment'] });
    http.post.mockResolvedValue({ accepted: true });
    render(<ItsmTicket alertId="A1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'itsm.recomment' }));
    await waitFor(() => expect(http.post).toHaveBeenCalledOnce());
    expect(http.post.mock.calls[0][0]).toBe('/alerts/api/action_execution/itsm_recomment/');
  });

});
