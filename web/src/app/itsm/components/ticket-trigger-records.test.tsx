import React, { StrictMode } from 'react';
import { App, Tabs } from 'antd';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import commonZh from '@/locales/zh.json';
import itsmZh from '../locales/zh.json';
import { TicketTriggerRecords } from './ticket-trigger-records';

const getTicketTriggerLogs = vi.hoisted(() => vi.fn());
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => ({ ready: true, getTicketTriggerLogs }) }));

const firstAction = {
  id: 1, trigger_name: '归档规则', event: 'ticket_end', action: 'tag', position: 1,
  status: 'success', message: '已添加归档标签', created_at: '2026-11-12T08:00:00Z',
};
const secondAction = {
  ...firstAction, id: 2, action: 'notice', position: 2, status: 'failed', message: '通知渠道暂不可用',
};

const messages = {
  ...Object.fromEntries(Object.entries(itsmZh.itsm.ticket).map(([key, value]) => [`itsm.ticket.${key}`, value])),
  ...Object.fromEntries(Object.entries(itsmZh.itsm.rule).map(([key, value]) => [`itsm.rule.${key}`, value])),
  'common.retry': commonZh.common.retry,
  'common.total': commonZh.common.total,
  'common.items': commonZh.common.items,
};

function panel(refreshKey = 0) {
  return <StrictMode><IntlProvider locale="zh" messages={messages}><App><Tabs defaultActiveKey="history" items={[
    { key: 'history', label: '流转日志', children: <p>流转日志内容</p> },
    {
      key: 'triggers', label: '触发器', destroyOnHidden: true,
      children: <TicketTriggerRecords ticketId={17} refreshKey={refreshKey} />,
    },
  ]} /></App></IntlProvider></StrictMode>;
}

beforeEach(() => {
  getTicketTriggerLogs.mockReset();
  window.matchMedia = vi.fn().mockImplementation(() => ({
    matches: false, addListener: vi.fn(), removeListener: vi.fn(),
  }));
});
afterEach(cleanup);

describe('工单触发器执行记录', () => {
  it('首次打开页签时加载，按执行顺序展示动作、结果和失败原因', async () => {
    getTicketTriggerLogs.mockResolvedValue({ items: [firstAction, secondAction], count: 2 });
    render(panel());
    expect(getTicketTriggerLogs).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('tab', { name: '触发器' }));
    const list = await screen.findByRole('list', { name: '触发器执行记录' });
    const rows = within(list).getAllByRole('listitem');
    expect(rows.map(row => row.textContent)).toEqual([
      expect.stringContaining('第 1 步'),
      expect.stringContaining('第 2 步'),
    ]);
    expect(within(rows[0]).getByText('工单结束')).toBeTruthy();
    expect(within(rows[0]).getByText('成功')).toBeTruthy();
    expect(within(rows[1]).getByText('失败')).toBeTruthy();
    expect(within(rows[1]).getByText('通知渠道暂不可用')).toBeTruthy();
    expect(getTicketTriggerLogs).toHaveBeenCalledTimes(1);
  });

  it('使用服务端分页，并在工单刷新后更新当前页', async () => {
    getTicketTriggerLogs
      .mockResolvedValueOnce({ items: [firstAction], count: 22 })
      .mockResolvedValueOnce({ items: [{ ...secondAction, status: 'pending' }], count: 22 })
      .mockResolvedValueOnce({ items: [secondAction], count: 22 });
    const { rerender } = render(panel());
    fireEvent.click(screen.getByRole('tab', { name: '触发器' }));
    await screen.findByText('已添加归档标签');

    fireEvent.click(screen.getByTitle('2'));
    await screen.findByText('等待执行');
    expect(getTicketTriggerLogs.mock.calls).toEqual([[17, 1, 20], [17, 2, 20]]);

    rerender(panel(1));
    await screen.findByText('失败');
    expect(getTicketTriggerLogs.mock.calls).toEqual([[17, 1, 20], [17, 2, 20], [17, 2, 20]]);
  });

  it('加载失败后支持重试并显示空状态', async () => {
    getTicketTriggerLogs
      .mockRejectedValueOnce(new Error('请求失败'))
      .mockResolvedValueOnce({ items: [], count: 0 });
    render(panel());
    fireEvent.click(screen.getByRole('tab', { name: '触发器' }));

    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('执行记录加载失败'));
    fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }));
    expect(await screen.findByText('暂无触发器执行记录')).toBeTruthy();
  });
});
