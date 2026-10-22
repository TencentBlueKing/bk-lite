import React, { useEffect, useRef } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  useCommon: () => ({ userList: [], levelList: [] }),
}));
vi.mock('@/context/userInfo', () => ({ useUserInfoContext: () => ({ username: 'admin' }) }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('next/dynamic', () => ({
  default: () => function Editor({
    value,
    onChange,
    onLoad,
    onFocus,
  }: {
    value: string;
    onChange?: (next: string) => void;
    onFocus?: () => void;
    onLoad?: (editor: {
      session: { insert: (position: { row: number; column: number }, text: string) => void };
      getCursorPosition: () => { row: number; column: number };
      focus: () => void;
    }) => void;
  }) {
    const valueRef = useRef(value);
    valueRef.current = value;
    useEffect(() => {
      onLoad?.({
        session: {
          insert: (position, text) => {
            const lines = valueRef.current.split('\n');
            const row = Math.min(position.row, Math.max(lines.length - 1, 0));
            const line = lines[row] ?? '';
            const column = Math.min(position.column, line.length);
            lines[row] = `${line.slice(0, column)}${text}${line.slice(column)}`;
            onChange?.(lines.join('\n'));
          },
        },
        getCursorPosition: () => ({ row: 2, column: 2 }),
        focus: () => undefined,
      });
    }, [onChange, onLoad]);
    return <textarea aria-label="template-editor" value={value} readOnly onFocus={() => onFocus?.()} />;
  },
}));

const body = '第一行\n第二行\n第三行尾部\n第四行';

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
  api.previewNotificationTemplate.mockResolvedValue({ subject: '', body: '', missing_fields: [] });
  api.getChannelList.mockResolvedValue([]);
  api.getNotificationTemplateCatalog.mockResolvedValue({
    variables: [{ path: 'event.latest_title', label: '最近事件标题' }],
  });
  api.getNotificationTemplate.mockResolvedValue({
    id: 4,
    name: '生产严重告警',
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
      body_template: body,
    }],
    updated_at: '2026-09-09T00:00:00Z',
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('通知模板变量插入', () => {
  it('把变量插到正文光标所在行，而不是追加到末尾', async () => {
    render(<TemplateEditor templateId="4" />);

    await waitFor(() => {
      expect((screen.getByLabelText('template-editor') as HTMLTextAreaElement).value).toBe(body);
    });

    fireEvent.click(screen.getByRole('button', { name: '最近事件标题' }));

    expect((screen.getByLabelText('template-editor') as HTMLTextAreaElement).value).toBe(
      '第一行\n第二行\n第三{{ event.latest_title }}行尾部\n第四行',
    );
  });

  it('光标在标题里时，把变量插到标题光标处', async () => {
    const subject = '【通知】标题尾部';
    api.getNotificationTemplate.mockResolvedValue({
      id: 4,
      name: '生产严重告警',
      description: '',
      team: [1],
      scope: 'single_alert',
      is_global: false,
      is_builtin: false,
      assignment_count: 0,
      revision: 1,
      contents: [{
        channel_type: 'email',
        subject_template: subject,
        body_template: body,
      }],
      updated_at: '2026-09-09T00:00:00Z',
    });

    render(<TemplateEditor templateId="4" />);

    const input = await screen.findByDisplayValue(subject) as HTMLInputElement;
    fireEvent.focus(input);
    input.setSelectionRange(4, 4);
    fireEvent.click(screen.getByRole('button', { name: '最近事件标题' }));

    expect(screen.getByDisplayValue('【通知】{{ event.latest_title }}标题尾部')).toBeTruthy();
    expect((screen.getByLabelText('template-editor') as HTMLTextAreaElement).value).toBe(body);
  });

  it('光标回到正文后，变量重新写入正文', async () => {
    render(<TemplateEditor templateId="4" />);

    const input = await screen.findByDisplayValue('标题') as HTMLInputElement;
    fireEvent.focus(input);
    input.setSelectionRange(1, 1);
    fireEvent.focus(screen.getByLabelText('template-editor'));
    fireEvent.click(screen.getByRole('button', { name: '最近事件标题' }));

    expect((input as HTMLInputElement).value).toBe('标题');
    expect((screen.getByLabelText('template-editor') as HTMLTextAreaElement).value).toBe(
      '第一行\n第二行\n第三{{ event.latest_title }}行尾部\n第四行',
    );
  });

  it('颜色参考按当前渠道给出可抄写法，并插入正文', async () => {
    render(<TemplateEditor templateId="4" />);
    await screen.findByLabelText('template-editor');
    fireEvent.click(screen.getByRole('button', { name: /colorTip$/ }));

    expect(await screen.findByText('<strong style="color:#F43B2C;">{{ alert.level }}</strong>')).toBeTruthy();

    fireEvent.click(screen.getAllByRole('button', { name: 'settings.notificationTemplate.colorTipInsert' })[1]);

    expect((screen.getByLabelText('template-editor') as HTMLTextAreaElement).value).toContain(
      '<strong style="color:#F43B2C;">{{ alert.level }}</strong>',
    );
  });

  it('告警详情链接悬停展示完整地址，点击后按光标插入', async () => {
    render(<TemplateEditor templateId="4" />);
    const hint = await screen.findByRole('button', { name: 'settings.notificationTemplate.alertDetailLinkHint' });
    const detailLink = `${window.location.origin}/alarm/alarms?alert_id={{ alert.alert_id }}`;

    fireEvent.mouseEnter(hint);
    expect(await screen.findByText(detailLink)).toBeTruthy();

    fireEvent.click(hint);
    expect((screen.getByLabelText('template-editor') as HTMLTextAreaElement).value).toBe(
      `第一行\n第二行\n第三${detailLink}行尾部\n第四行`,
    );
  });
});
