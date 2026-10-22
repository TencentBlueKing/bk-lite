import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Modal } from 'antd';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  alertActionOperate: vi.fn(),
  incidentActionOperate: vi.fn(),
  getActionRuleList: vi.fn(),
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { username: 'op1' } } }),
}));
vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) =>
      ({
        'alarms.close': '关闭',
        'alarms.alert': '告警',
        'alarms.incident': '事故',
        'alarms.reassign': '转派',
        'alarms.closeReasonLabel': '关闭原因',
        'alarms.closeReasonPlaceholder': '请输入关闭原因',
        'common.confirm': '确认',
        'common.cancel': '取消',
        'alarmCommon.success': '成功',
        'alarmCommon.partialFailure': '部分失败',
      })[key] || fallback || key,
  }),
}));
vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({ isSuperUser: false, loading: false }),
}));
vi.mock('@/hooks/usePermissions', () => ({
  default: () => ({ hasPermission: () => true }),
}));
vi.mock('@/app/alarm/api/alarms', () => ({
  useAlarmApi: () => ({ alertActionOperate: api.alertActionOperate }),
}));
vi.mock('@/app/alarm/api/incidents', () => ({
  useIncidentsApi: () => ({ incidentActionOperate: api.incidentActionOperate }),
}));
vi.mock('@/app/alarm/api/settings', () => ({
  useSettingApi: () => ({
    getActionRuleList: api.getActionRuleList,
    manualTriggerAction: vi.fn(),
  }),
}));
vi.mock('@/app/alarm/context/common', () => ({
  useCommon: () => ({ userList: [] }),
}));

import AlarmAction from '../alarmAction';

const processingAlert = {
  alert_id: 'A1',
  status: 'processing',
  operator: ['op1'],
  team: [1],
};

afterEach(() => {
  cleanup();
  api.alertActionOperate.mockReset();
  api.incidentActionOperate.mockReset();
  api.getActionRuleList.mockReset();
});

beforeAll(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
});

const openCloseDialog = async () => {
  render(<AlarmAction rowData={[processingAlert]} onAction={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: '关闭' }));
  await screen.findByText('关闭原因');
  return screen.getByPlaceholderText('请输入关闭原因');
};

it('手动关闭可以不填原因，请求里不带 reason', async () => {
  api.alertActionOperate.mockResolvedValue({ A1: { result: true } });
  api.getActionRuleList.mockResolvedValue({ items: [] });
  const input = await openCloseDialog();
  expect(input).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /确\s*认/ }));

  await waitFor(() => {
    expect(api.alertActionOperate).toHaveBeenCalledWith('close', {
      alert_id: ['A1'],
      assignee: [],
    });
  });
});

it('填写的关闭原因会随关闭请求提交，只含空白时不提交', async () => {
  api.alertActionOperate.mockResolvedValue({ A1: { result: true } });
  api.getActionRuleList.mockResolvedValue({ items: [] });
  const onAction = vi.fn();
  render(<AlarmAction rowData={[processingAlert]} onAction={onAction} />);
  fireEvent.click(screen.getByRole('button', { name: '关闭' }));
  const input = await screen.findByPlaceholderText('请输入关闭原因');

  fireEvent.change(input, { target: { value: '   ' } });
  fireEvent.click(screen.getByRole('button', { name: /确\s*认/ }));
  await waitFor(() => expect(api.alertActionOperate).toHaveBeenCalledTimes(1));
  expect(api.alertActionOperate).toHaveBeenLastCalledWith('close', {
    alert_id: ['A1'],
    assignee: [],
  });

  fireEvent.click(screen.getByRole('button', { name: '关闭' }));
  const again = await screen.findByPlaceholderText('请输入关闭原因');
  fireEvent.change(again, { target: { value: '  磁盘已清理  ' } });
  fireEvent.click(screen.getByRole('button', { name: /确\s*认/ }));

  await waitFor(() => {
    expect(api.alertActionOperate).toHaveBeenLastCalledWith('close', {
      alert_id: ['A1'],
      assignee: [],
      reason: '磁盘已清理',
    });
  });
  await waitFor(() => expect(onAction).toHaveBeenCalled());
});

it('取消关闭不调用关闭接口', async () => {
  const input = await openCloseDialog();
  fireEvent.change(input, { target: { value: '先不关' } });
  fireEvent.click(screen.getByRole('button', { name: /取\s*消/ }));
  expect(api.alertActionOperate).not.toHaveBeenCalled();
});

it('事故关闭仍走确认框，不打开关闭原因', () => {
  const confirm = vi.spyOn(Modal, 'confirm').mockReturnValue({
    destroy: vi.fn(),
    update: vi.fn(),
  } as ReturnType<typeof Modal.confirm>);
  render(
    <AlarmAction
      from="incident"
      rowData={[{ incident_id: 'I1', status: 'processing', operator: ['op1'] }]}
      onAction={vi.fn()}
    />
  );
  fireEvent.click(screen.getByRole('button', { name: '关闭' }));
  expect(confirm).toHaveBeenCalled();
  const reasonInput = screen.getByPlaceholderText('请输入关闭原因');
  expect((reasonInput.closest('.ant-modal-wrap') as HTMLElement).style.display).toBe('none');
  confirm.mockRestore();
});
