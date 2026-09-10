import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TemplateEditor from '../templateEditor';

const api = vi.hoisted(() => ({
  getNotificationTemplateCatalog: vi.fn(),
  getChannelList: vi.fn(),
  getNotificationTemplate: vi.fn(),
  previewNotificationTemplate: vi.fn(),
  createNotificationTemplate: vi.fn(),
  updateNotificationTemplate: vi.fn(),
  testSendNotificationTemplate: vi.fn(),
  testSendDraftNotificationTemplate: vi.fn(),
}));
const alarmApi = vi.hoisted(() => ({ getAlarmList: vi.fn() }));

vi.mock('@/app/alarm/api/settings', () => ({ useSettingApi: () => api }));
vi.mock('@/app/alarm/api/alarms', () => ({ useAlarmApi: () => alarmApi }));
vi.mock('@/app/alarm/context/common', () => ({
  useCommon: () => ({
    userList: [
      { id: '1', username: 'admin', display_name: '管理员' },
      { id: '2', username: 'alice', display_name: 'Alice' },
    ],
  }),
}));
vi.mock('@/context/userInfo', () => ({ useUserInfoContext: () => ({ username: 'admin' }) }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('next/dynamic', () => ({
  default: () => function Editor({ value }: { value: string }) {
    return <textarea aria-label="template-editor" value={value} readOnly />;
  },
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
  api.previewNotificationTemplate.mockResolvedValue({ subject: '', body: '', missing_fields: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('通知模板组编辑初始化', () => {
  it('新建页保留测试发送并加载真实告警候选', async () => {
    api.getNotificationTemplateCatalog.mockResolvedValue({ variables: [] });
    api.getChannelList.mockResolvedValue([
      { id: 5, name: '团队邮件【Email】', channel_type: 'email', team: [1] },
    ]);
    alarmApi.getAlarmList.mockResolvedValue({
      items: [{
        id: 18,
        alert_id: 'ALERT-REAL-018',
        title: '生产数据库连接数过高',
        resource_name: '生产数据库 01',
        level: '2',
      }],
    });

    render(<TemplateEditor />);

    const testButton = await screen.findByRole('button', { name: 'settings.notificationTemplate.testSend' });
    fireEvent.click(testButton);

    await waitFor(() => expect(alarmApi.getAlarmList).toHaveBeenCalledWith({ page: 1, page_size: 50 }));
    expect(screen.getByText('settings.notificationTemplate.testAlert')).toBeTruthy();
    expect(screen.getByText('settings.notificationTemplate.testAlertHint')).toBeTruthy();
    expect(screen.getByText('settings.notificationTemplate.testReceivers')).toBeTruthy();
    expect(screen.getByRole('combobox', { name: 'settings.notificationTemplate.testReceivers' })).toBeTruthy();

    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'settings.notificationTemplate.testAlert' }));
    fireEvent.click(await screen.findByText('[ALERT-REAL-018] 生产数据库连接数过高 · 生产数据库 01'));
    const submitButton = document.querySelector<HTMLButtonElement>('.ant-modal-footer .ant-btn-primary');
    expect(submitButton).toBeTruthy();
    fireEvent.click(submitButton!);

    await waitFor(() => expect(api.testSendDraftNotificationTemplate).toHaveBeenCalledWith({
      channel_id: 5,
      alert_id: 18,
      receivers: ['admin'],
      scope: 'single_alert',
      channel_type: 'email',
      subject_template: expect.stringContaining('{{ alert.title }}'),
      body_template: expect.stringContaining('{{ alert.content }}'),
    }));
  });

  it('详情返回前不可保存，返回后再展示真实内容', async () => {
    const detail = deferred<any>();
    api.getNotificationTemplateCatalog.mockResolvedValue({ variables: [] });
    api.getChannelList.mockResolvedValue([]);
    api.getNotificationTemplate.mockReturnValue(detail.promise);

    render(<TemplateEditor templateId="4" />);

    expect((screen.getByRole('button', { name: /common.save/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByText('settings.notificationTemplate.basicInfo')).toBeNull();

    await act(async () => detail.resolve({
      id: 4,
      name: '生产严重告警',
      description: '编辑详情',
      team: [1],
      scope: 'single_alert',
      is_global: false,
      is_builtin: false,
      assignment_count: 1,
      revision: 2,
      contents: [{
        channel_type: 'email',
        subject_template: '告警标题',
        body_template: '<p>告警正文</p>',
      }],
      updated_at: '2026-09-09T00:00:00Z',
    }));

    expect(await screen.findByDisplayValue('生产严重告警')).toBeTruthy();
    expect((screen.getByRole('button', { name: /common.save/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('变量目录或测试渠道失败不阻断模板详情加载', async () => {
    api.getNotificationTemplateCatalog.mockRejectedValue(new Error('catalog unavailable'));
    api.getChannelList.mockRejectedValue(new Error('channels unavailable'));
    api.getNotificationTemplate.mockResolvedValue({
      id: 4,
      name: '仍可编辑的模板',
      description: '',
      team: [1],
      scope: 'single_alert',
      is_global: false,
      is_builtin: false,
      assignment_count: 0,
      revision: 1,
      contents: [{
        channel_type: 'email',
        subject_template: '标题',
        body_template: '<p>正文</p>',
      }],
      updated_at: '2026-09-09T00:00:00Z',
    });

    render(<TemplateEditor templateId="4" />);

    await waitFor(() => expect(api.getNotificationTemplate).toHaveBeenCalledWith('4'));
    expect(await screen.findByDisplayValue('仍可编辑的模板')).toBeTruthy();
    expect((screen.getByRole('button', { name: /common.save/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('告警操作内置模板只展示一个具体通知渠道选择框', async () => {
    api.getNotificationTemplateCatalog.mockResolvedValue({ variables: [] });
    api.getChannelList.mockResolvedValue([
      { id: 5, name: '团队邮件【Email】', channel_type: 'email' },
      { id: 6, name: '团队企微【Enterprise Wechat Bot】', channel_type: 'enterprise_wechat_bot' },
    ]);
    api.getNotificationTemplate.mockResolvedValue({
      id: 9,
      name: '告警操作通知',
      description: '用于人工分派和转派告警时通知新的处理人。',
      team: [1],
      scope: 'alert_operation',
      is_global: false,
      builtin_key: 'alert_operation:1',
      is_builtin: true,
      channel_id: 5,
      assignment_count: 0,
      revision: 1,
      contents: [{
        channel_type: 'email',
        subject_template: '操作通知',
        body_template: '<p>操作正文</p>',
      }],
      updated_at: '2026-09-09T00:00:00Z',
    });

    render(<TemplateEditor templateId="9" />);

    expect(await screen.findByText('settings.notificationTemplate.operationChannelHint')).toBeTruthy();
    expect(screen.queryByText('settings.notificationTemplate.channelVersionHint')).toBeNull();
    expect(screen.getByRole('heading', { name: 'settings.notificationTemplate.operationEditorTitle' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'settings.notificationTemplate.backToTemplates' })).toBeTruthy();
    expect(screen.queryByLabelText('settings.notificationTemplate.name')).toBeNull();
    expect(screen.getAllByRole('combobox')).toHaveLength(1);
    expect(screen.getByTitle('settings.notificationTemplate.preview').className).toContain('min-h-[520px]');
    expect(screen.getByTitle('settings.notificationTemplate.preview').className).toContain('max-h-[800px]');

    api.updateNotificationTemplate.mockResolvedValue({});
    fireEvent.click(screen.getByRole('button', { name: /common.save/ }));
    await waitFor(() => expect(api.updateNotificationTemplate).toHaveBeenCalledWith(
      '9',
      expect.objectContaining({
        scope: 'alert_operation',
        channel_id: 5,
        contents: [expect.objectContaining({ channel_type: 'email' })],
      }),
    ));
  });
});
