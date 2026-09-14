import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OperateModal from '../operateModal';

const api = vi.hoisted(() => ({
  getChannelList: vi.fn(),
  getNotificationTemplateOptions: vi.fn(),
  createAssignment: vi.fn(),
  updateAssignment: vi.fn(),
}));
vi.mock('@/app/alarm/api/settings', () => ({ useSettingApi: () => api }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/alarm/context/common', () => ({
  useCommon: () => ({ levelList: [], levelMap: {}, userList: [] }),
}));
vi.mock('@/app/alarm/(pages)/settings/components/matchRule', () => ({ default: () => null }));
vi.mock('@/app/alarm/(pages)/settings/components/effectiveTime', () => ({
  default: () => null, defaultEffectiveTime: {},
}));
vi.mock('../escalationChain', () => ({ default: () => null }));
vi.mock('../notificationTargetFields', () => ({ default: () => null }));
vi.mock('@/app/alarm/components/levelIcon', () => ({ default: () => null }));

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false, addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
  });
});
beforeEach(() => {
  vi.clearAllMocks();
  api.getChannelList.mockResolvedValue([]);
  api.getNotificationTemplateOptions.mockResolvedValue([]);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('分派策略通知渠道', () => {
  it('无可用渠道时展示配置说明和入口', async () => {
    render(<OperateModal open onClose={vi.fn()} />);
    expect(await screen.findByText('settings.assignStrategy.noChannels')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'settings.assignStrategy.configureChannels' }).getAttribute('href'))
      .toBe('/system-manager/channel');
  });

  it('加载失败时可以重试，并恢复渠道选择', async () => {
    api.getChannelList.mockRejectedValueOnce(new Error('unavailable'));
    render(<OperateModal open onClose={vi.fn()} />);
    expect(await screen.findByText('settings.assignStrategy.channelLoadFailed')).toBeTruthy();
    expect(screen.queryByText('settings.assignStrategy.noChannels')).toBeNull();
    api.getChannelList.mockResolvedValue([{ id: 1, name: '运维邮件', channel_type: 'email' }]);
    fireEvent.click(screen.getByRole('button', { name: 'settings.assignStrategy.retryChannels' }));
    expect(await screen.findByRole('checkbox', { name: '运维邮件' })).toBeTruthy();
    expect(screen.queryByText('settings.assignStrategy.channelLoadFailed')).toBeNull();
  });

  it('模板加载失败不影响已加载的渠道及默认选择', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    api.getChannelList.mockResolvedValue([{ id: 1, name: '运维邮件', channel_type: 'email' }]);
    api.getNotificationTemplateOptions.mockRejectedValueOnce(new Error('unavailable'));
    render(<OperateModal open onClose={vi.fn()} />);
    const checkbox = await screen.findByRole('checkbox', { name: '运维邮件' }) as HTMLInputElement;
    await waitFor(() => expect(checkbox.checked).toBe(true));
    expect(checkbox.disabled).toBe(false);
    expect(screen.queryByText('settings.assignStrategy.channelLoadFailed')).toBeNull();
    expect(screen.queryByText('settings.assignStrategy.noChannels')).toBeNull();
  });

  it('选择多个通知渠道时按渠道展示四个场景模板字段', async () => {
    api.getChannelList.mockResolvedValue([
      { id: 1, name: '运维邮件', channel_type: 'email' },
      { id: 2, name: '运维企微', channel_type: 'enterprise_wechat_bot' },
    ]);
    api.getNotificationTemplateOptions.mockResolvedValue([
      { id: 10, name: '生产告警' },
    ]);
    render(<OperateModal open onClose={vi.fn()} />);

    const wechat = await screen.findByRole('checkbox', { name: '运维企微' });
    fireEvent.click(wechat);

    expect(await screen.findByText('settings.notificationTemplate.bindingTitle')).toBeTruthy();
    expect(screen.getAllByRole('combobox')).toHaveLength(8);
    expect(screen.getAllByText('settings.notificationTemplate.sceneDefault')).toHaveLength(2);
    expect(screen.getAllByText('settings.notificationTemplate.sceneReminder')).toHaveLength(2);
    expect(screen.getAllByText('settings.notificationTemplate.sceneEscalation')).toHaveLength(2);
    expect(screen.getAllByText('settings.notificationTemplate.sceneRecovery')).toHaveLength(2);
  });

  it('重新打开时查询失败不会保留上一次的渠道选项', async () => {
    api.getChannelList.mockResolvedValueOnce([{ id: 1, name: '运维邮件', channel_type: 'email' }]);
    const onClose = vi.fn();
    const view = render(<OperateModal open onClose={onClose} />);
    expect(await screen.findByRole('checkbox', { name: '运维邮件' })).toBeTruthy();
    view.rerender(<OperateModal open={false} onClose={onClose} />);
    api.getChannelList.mockRejectedValueOnce(new Error('unavailable'));
    view.rerender(<OperateModal open onClose={onClose} />);
    expect(await screen.findByText('settings.assignStrategy.channelLoadFailed')).toBeTruthy();
    expect(screen.queryByRole('checkbox', { name: '运维邮件' })).toBeNull();
  });
});
