import React, { useState } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import NotificationRuleMatrix from '..';
import type { NoticeRuleDraft } from '@/app/patch-manager/types';

const messages = {
  'patchManager.settingsPage.periodicAssessmentNotice': '周期评估通知',
  'patchManager.settingsPage.periodicAssessmentNoticeHelp': '发现需关注项时发送汇总通知',
  'patchManager.settingsPage.noticeChannel': '通知方式',
  'patchManager.settingsPage.noticeChannelType': '渠道类型',
  'patchManager.settingsPage.noticeReceivers': '接收人',
  'patchManager.operation': '操作',
  'patchManager.settingsPage.selectNoticeChannel': '请选择通知方式',
  'patchManager.settingsPage.noticeChannelRequired': '请选择通知方式',
  'patchManager.settingsPage.selectNoticeReceivers': '请选择接收人',
  'patchManager.settingsPage.selectChannelFirst': '请先选择通知方式',
  'patchManager.settingsPage.noticeReceiversRequired': '请至少选择一位接收人',
  'patchManager.settingsPage.useChannelConfiguration': '使用渠道自身配置',
  'patchManager.settingsPage.deleteNoticeRule': '删除通知方式',
  'patchManager.settingsPage.firstNoticeRuleRequired': '至少保留一种通知方式',
  'patchManager.settingsPage.insertNoticeRule': '在下方添加通知方式',
  'patchManager.settingsPage.noMoreNoticeChannels': '暂无更多可添加的通知方式',
  'patchManager.settingsPage.channelType.email': '邮件',
  'patchManager.settingsPage.channelType.nats': 'NATS',
  'patchManager.delete': '删除',
};

function Harness() {
  const [notificationEnabled, setNotificationEnabled] = useState(false);
  const [rules, setRules] = useState<NoticeRuleDraft[]>([]);

  return (
    <IntlProvider locale="zh" messages={messages}>
      <NotificationRuleMatrix
        scheduleEnabled
        notificationEnabled={notificationEnabled}
        rules={rules}
        channels={[
          { id: 7, name: '运维邮箱', channel_type: 'email' },
          { id: 9, name: '自动化工作流', channel_type: 'nats' },
          { id: 10, name: '补丁告警机器人', channel_type: 'enterprise_wechat_bot' },
        ]}
        users={[
          { id: 11, username: 'alice', display_name: 'Alice' },
          { id: 12, username: 'bob', display_name: 'Bob' },
        ]}
        onNotificationEnabledChange={setNotificationEnabled}
        onRulesChange={setRules}
      />
      <output data-testid="rules-state">{JSON.stringify(rules)}</output>
    </IntlProvider>
  );
}

function ValidationHarness() {
  const [rules, setRules] = useState<NoticeRuleDraft[]>([
    { key: 'validation-rule', receivers: [] },
  ]);

  return (
    <IntlProvider locale="zh" messages={messages}>
      <NotificationRuleMatrix
        scheduleEnabled
        notificationEnabled
        showValidationErrors
        rules={rules}
        channels={[
          { id: 7, name: '运维邮箱', channel_type: 'email' },
          { id: 9, name: '自动化工作流', channel_type: 'nats' },
        ]}
        users={[{ id: 11, username: 'alice', display_name: 'Alice' }]}
        onNotificationEnabledChange={vi.fn()}
        onRulesChange={setRules}
      />
    </IntlProvider>
  );
}

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('周期评估通知规则矩阵', () => {
  it('每种通知方式维护独立接收人，NATS 使用渠道自身配置', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.queryByRole('combobox', { name: '通知方式 1' })).toBeNull();
    await user.click(screen.getByRole('switch', { name: '周期评估通知' }));
    expect(await screen.findByRole('combobox', { name: '通知方式 1' })).not.toBeNull();
    expect(screen.queryByRole('button', { name: '添加通知方式' })).toBeNull();

    await user.click(screen.getByRole('combobox', { name: '通知方式 1' }));
    await user.click(await screen.findByText('运维邮箱'));
    const firstRow = document.querySelector('[class*="ruleRow"]');
    expect(firstRow).not.toBeNull();
    expect(within(firstRow as HTMLElement).getByText('邮件')).not.toBeNull();
    await user.click(screen.getByRole('combobox', { name: '接收人 1' }));
    await user.click(await screen.findByText('Alice(alice)'));

    await user.click(screen.getByRole('button', { name: '在下方添加通知方式 1' }));
    await user.click(screen.getByRole('combobox', { name: '通知方式 2' }));
    const natsOptions = await screen.findAllByText('自动化工作流');
    await user.click(natsOptions[natsOptions.length - 1]);

    const rows = document.querySelectorAll('[class*="ruleRow"]');
    expect(rows).toHaveLength(2);
    expect(within(rows[1] as HTMLElement).getByText('使用渠道自身配置')).not.toBeNull();
    expect(screen.queryByRole('combobox', { name: '接收人 2' })).toBeNull();
    expect(JSON.parse(screen.getByTestId('rules-state').textContent || '[]')).toMatchObject([
      { channel_id: 7, receivers: [11] },
      { channel_id: 9, receivers: [] },
    ]);
  });

  it('点击加号时在当前通知方式下方插入新行，减号删除对应行', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('switch', { name: '周期评估通知' }));
    const firstDeleteButton = await screen.findByRole('button', { name: '删除通知方式 1' });
    expect((firstDeleteButton as HTMLButtonElement).disabled).toBe(true);

    await user.click(screen.getByRole('combobox', { name: '通知方式 1' }));
    await user.click(await screen.findByText('运维邮箱'));
    await user.click(screen.getByRole('button', { name: '在下方添加通知方式 1' }));
    await user.click(screen.getByRole('combobox', { name: '通知方式 2' }));
    const natsOptions = await screen.findAllByText('自动化工作流');
    await user.click(natsOptions[natsOptions.length - 1]);

    await user.click(screen.getByRole('button', { name: '在下方添加通知方式 1' }));

    const unavailableAddButton = screen.getByRole('button', { name: '暂无更多可添加的通知方式 1' });
    expect((unavailableAddButton as HTMLButtonElement).disabled).toBe(true);
    await user.hover(unavailableAddButton);
    expect((await screen.findByRole('tooltip')).textContent).toBe('暂无更多可添加的通知方式');

    expect(JSON.parse(screen.getByTestId('rules-state').textContent || '[]')).toMatchObject([
      { channel_id: 7 },
      { receivers: [] },
      { channel_id: 9 },
    ]);

    await user.click(screen.getByRole('button', { name: '删除通知方式 2' }));
    expect(JSON.parse(screen.getByTestId('rules-state').textContent || '[]')).toMatchObject([
      { channel_id: 7 },
      { channel_id: 9 },
    ]);
  });

  it('提交校验后以红色输入框和叹号提示表格必填项', async () => {
    const user = userEvent.setup();
    render(<ValidationHarness />);

    const channelErrorIcon = screen.getByLabelText('请选择通知方式');
    expect(channelErrorIcon).not.toBeNull();
    await user.hover(channelErrorIcon);
    expect((await screen.findByRole('tooltip')).textContent).toBe('请选择通知方式');

    await user.click(screen.getByRole('combobox', { name: '通知方式 1' }));
    await user.click(await screen.findByText('运维邮箱'));

    expect(screen.queryByLabelText('请选择通知方式')).toBeNull();
    const receiverErrorIcon = screen.getByLabelText('请至少选择一位接收人');
    expect(receiverErrorIcon).not.toBeNull();
    await user.hover(receiverErrorIcon);
    expect((await screen.findByRole('tooltip')).textContent).toBe('请至少选择一位接收人');
  });
});
