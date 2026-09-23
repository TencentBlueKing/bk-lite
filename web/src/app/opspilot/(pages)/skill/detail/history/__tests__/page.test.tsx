import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SkillHistoryPage from '../page';

const mockFetchSkillChannels = vi.fn();
const mockFetchAdminSkillConversations = vi.fn();
const mockFetchAdminSkillSessionMessages = vi.fn();

vi.mock('next/navigation', () => ({
  useSearchParams: () => ({
    get: (key: string) => (key === 'id' ? '123' : null),
  }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback || key,
  }),
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({
    convertToLocalizedTime: (value: string) => value,
  }),
}));

vi.mock('@/app/opspilot/api/skill', () => ({
  useSkillApi: () => ({
    fetchSkillChannels: mockFetchSkillChannels,
    fetchAdminSkillConversations: mockFetchAdminSkillConversations,
    fetchAdminSkillSessionMessages: mockFetchAdminSkillSessionMessages,
  }),
}));

vi.mock('@/app/opspilot/components/custom-chat-sse', () => ({
  default: ({ mode }: { mode?: string }) => (
    <div data-testid="readonly-chat" data-mode={mode}>
      只读对话
    </div>
  ),
}));

vi.mock('@/app/opspilot/components/custom-chat-sse/historyMessageProcessor', () => ({
  processHistoryMessageWithExtras: (content: string) => ({ content }),
}));

describe('SkillHistoryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
    mockFetchSkillChannels.mockResolvedValue([
      { id: 8, name: '生产企微', channel_type: 'enterprise_wechat' },
    ]);
    mockFetchAdminSkillConversations.mockResolvedValue({
      items: [
        {
          session_id: 's-1',
          title: '开权限申请',
          channel_id: 8,
          channel_type: 'enterprise_wechat',
          channel_name: '生产企微',
          person_display: '爱丽丝',
          count: 2,
          created_at: '2026-09-18T01:00:00Z',
          updated_at: '2026-09-18T01:00:00Z',
        },
      ],
      count: 1,
    });
    mockFetchAdminSkillSessionMessages.mockResolvedValue([
      { id: 1, conversation_role: 'user', conversation_content: '开权限', conversation_time: '2026-09-18T01:00:00Z' },
    ]);
  });

  afterEach(cleanup);

  it('renders right-aligned channel/user filters and bot-aligned columns', async () => {
    const { container } = render(<SkillHistoryPage />);

    await waitFor(() => {
      expect(mockFetchAdminSkillConversations).toHaveBeenCalled();
    });

    expect(screen.getByText('全部渠道')).toBeTruthy();
    expect(screen.getByPlaceholderText('请输入用户名进行搜索...')).toBeTruthy();
    expect(screen.queryByPlaceholderText('搜索会话标题')).toBeNull();
    expect(screen.queryByTestId('time-selector')).toBeNull();
    const headers = screen.getAllByRole('columnheader').map((node) => node.textContent);
    expect(headers.slice(0, 3)).toEqual(['渠道', '用户', '标题']);
    expect(headers).toEqual(['渠道', '用户', '标题', '创建时间', '更新时间', '数量', '操作']);
    expect(screen.getByText('开权限申请')).toBeTruthy();
    expect(screen.getByText('爱丽丝')).toBeTruthy();
    expect(screen.getByText('详情')).toBeTruthy();

    const toolbar = container.querySelector('.justify-end');
    expect(toolbar).toBeTruthy();

    const params = mockFetchAdminSkillConversations.mock.calls[0][0];
    expect(params.skill_id).toBe('123');
    expect(params.page_size).toBe(10);
    expect(params.start_time).toBeUndefined();
    expect(params.end_time).toBeUndefined();
    expect(params.title).toBeUndefined();
  });

  it('opens a read-only drawer without a send box', async () => {
    render(<SkillHistoryPage />);

    await waitFor(() => {
      expect(screen.getByText('开权限申请')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('详情'));

    await waitFor(() => {
      expect(mockFetchAdminSkillSessionMessages).toHaveBeenCalledWith('s-1');
      expect(screen.getByTestId('readonly-chat')).toBeTruthy();
    });
    expect(screen.getByTestId('readonly-chat').getAttribute('data-mode')).toBe('display');
    expect(screen.queryByPlaceholderText('chat.inputPlaceholder')).toBeNull();
    expect(screen.queryByText('发送')).toBeNull();
  });
});
