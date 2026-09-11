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
  default: () => null,
  defaultEffectiveTime: {},
}));
vi.mock('../escalationChain', () => ({ default: () => null }));
vi.mock('../notificationTargetFields', () => ({ default: () => null }));
vi.mock('@/app/alarm/components/levelIcon', () => ({ default: () => null }));

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
  vi.clearAllMocks();
  api.getChannelList.mockResolvedValue([]);
  api.getNotificationTemplateOptions.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('分派策略优先级', () => {
  it('新增策略默认优先级为100并限制输入范围', async () => {
    render(<OperateModal open onClose={vi.fn()} />);

    const priority = await screen.findByRole('spinbutton', {
      name: 'settings.assignStrategy.priority',
    }) as HTMLInputElement;

    expect(priority.value).toBe('100');
    expect(priority.getAttribute('aria-valuemin')).toBe('0');
    expect(priority.getAttribute('aria-valuemax')).toBe('100');
  });

  it('提交策略时携带用户填写的优先级', async () => {
    api.getChannelList.mockResolvedValue([
      { id: 1, name: '运维邮件', channel_type: 'email' },
    ]);
    api.createAssignment.mockResolvedValue({});
    render(<OperateModal open onClose={vi.fn()} />);

    fireEvent.change(screen.getByRole('textbox', { name: 'settings.assignName' }), {
      target: { value: '高优先级策略' },
    });
    const priority = await screen.findByRole('spinbutton', {
      name: 'settings.assignStrategy.priority',
    });
    fireEvent.change(priority, { target: { value: '80' } });
    await waitFor(() => {
      expect((screen.getByRole('checkbox', { name: '运维邮件' }) as HTMLInputElement).checked).toBe(true);
    });
    fireEvent.click(screen.getByRole('button', { name: 'settings.assignStrategy.submit' }));

    await waitFor(() => {
      expect(api.createAssignment).toHaveBeenCalledWith(expect.objectContaining({ priority: 80 }));
    });
  });
});
