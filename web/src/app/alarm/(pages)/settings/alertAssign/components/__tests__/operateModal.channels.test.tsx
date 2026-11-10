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
const commonState = vi.hoisted(() => ({
  levelList: [] as Array<{ level_id: string; level_display_name: string; icon: string }>,
  levelMap: {} as Record<string, string>,
  userList: [] as Array<{ display_name: string; username: string }>,
}));
vi.mock('@/app/alarm/api/settings', () => ({ useSettingApi: () => api }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/alarm/context/common', () => ({
  useCommon: () => commonState,
}));
vi.mock('@/app/alarm/(pages)/settings/components/matchRule', () => ({ default: () => null }));
vi.mock('@/app/alarm/(pages)/settings/components/effectiveTime', () => ({
  default: () => null, defaultEffectiveTime: {},
}));
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
  commonState.levelList = [];
  commonState.levelMap = {};
  api.getChannelList.mockResolvedValue([]);
  api.getNotificationTemplateOptions.mockResolvedValue([]);
});

const chooseTemplate = async (index: number) => {
  fireEvent.mouseDown(screen.getAllByRole('combobox')[index]);
  const option = await waitFor(() => {
    const dropdowns = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
    const node = dropdowns[dropdowns.length - 1]?.querySelector('.ant-select-item-option');
    expect(node).toBeTruthy();
    return node as Element;
  });
  fireEvent.click(option);
};

const expandAdvanced = () => {
  fireEvent.click(screen.getByText('alarmCommon.advanced'));
};
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

  const requiredClass = (label: string) => screen.getAllByText(label)[0].closest('label')?.className || '';

  it('四个场景始终可选，未开启时只有首次分派必填', async () => {
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
    expect(requiredClass('settings.notificationTemplate.sceneDefault')).toContain('ant-form-item-required');
    expect(requiredClass('settings.notificationTemplate.sceneReminder')).not.toContain('ant-form-item-required');
    expect(requiredClass('settings.notificationTemplate.sceneEscalation')).not.toContain('ant-form-item-required');
    expect(requiredClass('settings.notificationTemplate.sceneRecovery')).not.toContain('ant-form-item-required');
  });

  it('未开启其他场景时，只缺首次分派模板不能提交', async () => {
    api.getChannelList.mockResolvedValue([{ id: 1, name: '运维邮件', channel_type: 'email' }]);
    api.getNotificationTemplateOptions.mockResolvedValue([{ id: 10, name: '生产告警' }]);
    api.createAssignment.mockResolvedValue({});
    render(<OperateModal open onClose={vi.fn()} />);

    fireEvent.change(screen.getByRole('textbox', { name: 'settings.assignName' }), {
      target: { value: '夜间值班' },
    });
    await waitFor(() => {
      expect((screen.getByRole('checkbox', { name: '运维邮件' }) as HTMLInputElement).checked).toBe(true);
    });
    fireEvent.click(screen.getByRole('button', { name: 'settings.assignStrategy.submit' }));

    await waitFor(() => {
      expect(document.querySelectorAll('.ant-form-item-explain-error')).toHaveLength(1);
    });
    expect(api.createAssignment).not.toHaveBeenCalled();
  });

  it('未开启提醒、升级和恢复时也可以预选模板并保存', async () => {
    api.getChannelList.mockResolvedValue([{ id: 1, name: '运维邮件', channel_type: 'email' }]);
    api.getNotificationTemplateOptions.mockResolvedValue([{ id: 10, name: '生产告警' }]);
    api.createAssignment.mockResolvedValue({});
    render(<OperateModal open onClose={vi.fn()} />);

    fireEvent.change(screen.getByRole('textbox', { name: 'settings.assignName' }), {
      target: { value: '夜间值班' },
    });
    await waitFor(() => {
      expect(screen.getAllByRole('combobox')).toHaveLength(4);
    });
    await chooseTemplate(0);
    await chooseTemplate(3);
    fireEvent.click(screen.getByRole('button', { name: 'settings.assignStrategy.submit' }));

    await waitFor(() => {
      expect(api.createAssignment).toHaveBeenCalledWith(expect.objectContaining({
        notify_channels: [expect.objectContaining({
          notification_templates: { default: 10, recovery: 10 },
        })],
      }));
    });
  });

  it('勾选恢复后恢复模板变为必填', async () => {
    api.getChannelList.mockResolvedValue([{ id: 1, name: '运维邮件', channel_type: 'email' }]);
    api.getNotificationTemplateOptions.mockResolvedValue([{ id: 10, name: '生产告警' }]);
    api.createAssignment.mockResolvedValue({});
    render(<OperateModal open onClose={vi.fn()} />);

    fireEvent.change(screen.getByRole('textbox', { name: 'settings.assignName' }), {
      target: { value: '夜间值班' },
    });
    await waitFor(() => expect(screen.getAllByRole('combobox')).toHaveLength(4));
    expandAdvanced();
    fireEvent.click(screen.getByRole('checkbox', { name: 'settings.assignStrategy.recovery' }));

    await waitFor(() => {
      expect(requiredClass('settings.notificationTemplate.sceneRecovery')).toContain('ant-form-item-required');
    });
    await chooseTemplate(0);
    fireEvent.click(screen.getByRole('button', { name: 'settings.assignStrategy.submit' }));
    await waitFor(() => {
      expect(document.querySelectorAll('.ant-form-item-explain-error')).toHaveLength(1);
    });
    expect(document.querySelector('.ant-form-item-explain-error')?.textContent).toBe('common.selectTip');
    expect(api.createAssignment).not.toHaveBeenCalled();
  });

  it('提醒间隔大于 0 后提醒模板变为必填', async () => {
    commonState.levelList = [{ level_id: '1', level_display_name: '严重', icon: '' }];
    commonState.levelMap = { '1': 'red' };
    api.getChannelList.mockResolvedValue([{ id: 1, name: '运维邮件', channel_type: 'email' }]);
    api.getNotificationTemplateOptions.mockResolvedValue([{ id: 10, name: '生产告警' }]);
    render(<OperateModal open onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getAllByRole('combobox')).toHaveLength(4));
    expect(requiredClass('settings.notificationTemplate.sceneReminder')).not.toContain('ant-form-item-required');
    expandAdvanced();
    const interval = screen.getAllByRole('spinbutton').find(
      (node) => node.getAttribute('aria-label') !== 'settings.assignStrategy.priority',
    );
    expect(interval).toBeTruthy();
    fireEvent.change(interval as HTMLElement, { target: { value: '5' } });

    await waitFor(() => {
      expect(requiredClass('settings.notificationTemplate.sceneReminder')).toContain('ant-form-item-required');
    });
  });

  it('打开告警升级后升级模板变为必填', async () => {
    api.getChannelList.mockResolvedValue([{ id: 1, name: '运维邮件', channel_type: 'email' }]);
    api.getNotificationTemplateOptions.mockResolvedValue([{ id: 10, name: '生产告警' }]);
    render(<OperateModal open onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getAllByRole('combobox')).toHaveLength(4));
    expandAdvanced();
    fireEvent.click(screen.getByRole('switch', { name: 'settings.assignStrategy.escalation' }));

    await waitFor(() => {
      expect(requiredClass('settings.notificationTemplate.sceneEscalation')).toContain('ant-form-item-required');
    });
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
