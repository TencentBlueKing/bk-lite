import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SkillChannelPage from '../page';

const mockChannels = [
  {
    id: 1,
    name: 'IT运维助手',
    channel_type: 'platform',
    enabled: true,
  },
  {
    id: 2,
    name: '企微客服',
    channel_type: 'enterprise_wechat',
    enabled: false,
    channel_config: {
      token: 'test-token',
    },
  },
  {
    id: 3,
    name: '网页在线咨询',
    channel_type: 'web_chat',
    enabled: true,
  },
];

const mockFetchSkillChannels = vi.fn();
const mockCreateSkillChannel = vi.fn();
const mockUpdateSkillChannel = vi.fn();
const mockSetSkillChannelEnabled = vi.fn();
const mockDeleteSkillChannel = vi.fn();

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

vi.mock('@/app/opspilot/api/skill', () => ({
  useSkillApi: () => ({
    fetchSkillChannels: mockFetchSkillChannels,
    createSkillChannel: mockCreateSkillChannel,
    updateSkillChannel: mockUpdateSkillChannel,
    setSkillChannelEnabled: mockSetSkillChannelEnabled,
    deleteSkillChannel: mockDeleteSkillChannel,
  }),
}));

vi.mock('@/components/permission', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/app/(core)/components/global-webchat/apps-changed', () => ({
  notifyWebchatAppsChanged: vi.fn(),
}));

describe('SkillChannelPage', () => {
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
    mockFetchSkillChannels.mockResolvedValue([...mockChannels]);
  });

  afterEach(cleanup);

  it('renders skeleton loading screen initially', () => {
    mockFetchSkillChannels.mockReturnValue(new Promise(() => {}));
    render(<SkillChannelPage />);

    expect(screen.getByLabelText('loading')).toBeTruthy();
  });

  it('renders stats, table rows, and toolbar', async () => {
    render(<SkillChannelPage />);

    await waitFor(() => {
      expect(mockFetchSkillChannels).toHaveBeenCalledWith('123');
    });

    // 指标卡
    expect(screen.getByText('渠道总数')).toBeTruthy();
    expect(screen.getAllByText('已启用').length).toBeGreaterThan(0);
    expect(screen.getAllByText('未启用').length).toBeGreaterThan(0);

    // 表格内容
    expect(screen.getByText('IT运维助手')).toBeTruthy();
    expect(screen.getByText('企微客服')).toBeTruthy();
    expect(screen.getByText('网页在线咨询')).toBeTruthy();

    // 工具栏操作
    expect(screen.getByText('添加渠道')).toBeTruthy();
    expect(screen.getByPlaceholderText('按名称筛选')).toBeTruthy();
  });

  it('filters by channel name keyword', async () => {
    render(<SkillChannelPage />);

    await waitFor(() => {
      expect(screen.getByText('IT运维助手')).toBeTruthy();
    });

    const searchInput = screen.getByPlaceholderText('按名称筛选');
    fireEvent.change(searchInput, { target: { value: '企微' } });

    expect(screen.getByText('企微客服')).toBeTruthy();
    expect(screen.queryByText('IT运维助手')).toBeNull();
  });

  it('opens create modal when clicking add channel', async () => {
    render(<SkillChannelPage />);

    await waitFor(() => {
      expect(screen.getByText('IT运维助手')).toBeTruthy();
    });

    const addButtons = screen.getAllByRole('button', { name: /添加渠道/ });
    fireEvent.click(addButtons[0]);

    // 弹窗表单项
    await waitFor(() => {
      expect(screen.getByPlaceholderText('选填，便于识别不同入口')).toBeTruthy();
    });
  });

  it('toggles channel enabled state', async () => {
    mockSetSkillChannelEnabled.mockResolvedValue({ success: true });
    render(<SkillChannelPage />);

    await waitFor(() => {
      expect(screen.getByText('IT运维助手')).toBeTruthy();
    });

    const switches = screen.getAllByRole('switch');
    fireEvent.click(switches[0]);

    await waitFor(() => {
      expect(mockSetSkillChannelEnabled).toHaveBeenCalledWith(1, false);
    });
  });

  it('shows empty state when no channels returned', async () => {
    mockFetchSkillChannels.mockResolvedValue([]);
    render(<SkillChannelPage />);

    await waitFor(() => {
      expect(screen.getByText('尚未发布任何渠道')).toBeTruthy();
    });
  });

  it('opens edit modal with existing values', async () => {
    render(<SkillChannelPage />);

    await waitFor(() => {
      expect(screen.getByText('企微客服')).toBeTruthy();
    });

    const editButtons = screen.getAllByText('设置');
    fireEvent.click(editButtons[1]); // 第二个是企微客服

    await waitFor(() => {
      const input = screen.getByDisplayValue('企微客服');
      expect(input).toBeTruthy();
    });
  });
});
