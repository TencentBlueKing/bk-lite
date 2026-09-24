import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { message } from 'antd';
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
    public_id: '11111111-1111-4111-8111-111111111111',
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
  {
    id: 4,
    public_id: '22222222-2222-4222-8222-222222222222',
    name: 'dddd',
    channel_type: 'embedded_chat',
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

  it('opens the clicked web chat channel in the new window', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('11111111-1111-4111-8111-111111111111');
    render(<SkillChannelPage />);

    await waitFor(() => {
      expect(screen.getByText('网页在线咨询')).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: '对话' }));
    expect(openSpy).toHaveBeenCalledWith(
      '/opspilot/skill/chat?entry=11111111-1111-4111-8111-111111111111',
      '_blank',
      'noopener,noreferrer'
    );
    expect(localStorage.getItem('opspilot.webChatEntry')).toContain(
      '"11111111-1111-4111-8111-111111111111":"3"'
    );
    expect(openSpy.mock.calls[0][0]).not.toContain('channel=');
    openSpy.mockRestore();
    localStorage.removeItem('opspilot.webChatEntry');
  });

  it('keeps list actions to edit/delete, plus chat for web', async () => {
    render(<SkillChannelPage />);

    await waitFor(() => {
      expect(screen.getByText('网页在线咨询')).toBeTruthy();
    });

    expect(screen.getByRole('button', { name: '对话' })).toBeTruthy();
    expect(screen.getAllByText('编辑').length).toBe(4);
    expect(screen.queryByRole('button', { name: '链接' })).toBeNull();
    expect(screen.queryByRole('button', { name: '文档' })).toBeNull();
    expect(screen.queryByRole('button', { name: '回调' })).toBeNull();
    expect(screen.queryByText('设置')).toBeNull();
  });

  it('copies embedded chat url from the edit modal', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const successSpy = vi.spyOn(message, 'success');

    render(<SkillChannelPage />);

    await waitFor(() => {
      expect(screen.getByText('dddd')).toBeTruthy();
    });

    fireEvent.click(screen.getAllByText('编辑')[3]);

    await waitFor(() => {
      expect(screen.getByDisplayValue(
        `${window.location.origin}/api/v1/opspilot/skill_channel/embedded/123/22222222-2222-4222-8222-222222222222/`
      )).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: '复制' }));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(
        `${window.location.origin}/api/v1/opspilot/skill_channel/embedded/123/22222222-2222-4222-8222-222222222222/`
      );
      expect(successSpy).toHaveBeenCalledWith('复制成功');
    });
    successSpy.mockRestore();

    const docsLink = screen.getByRole('link', { name: '接入文档 →' });
    expect(docsLink.getAttribute('href')).toContain('/opspilot/skill/detail/api?id=123');
  });

  it('shows copyable callback url when editing an IM channel', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const successSpy = vi.spyOn(message, 'success');

    render(<SkillChannelPage />);

    await waitFor(() => {
      expect(screen.getByText('企微客服')).toBeTruthy();
    });

    fireEvent.click(screen.getAllByText('编辑')[1]);

    const expectedUrl = `${window.location.origin}/api/v1/opspilot/skill_channel/11111111-1111-4111-8111-111111111111/enterprise_wechat/`;
    await waitFor(() => {
      expect(screen.getByDisplayValue(expectedUrl)).toBeTruthy();
      expect(
        screen.getByText('复制此地址到企微 / 钉钉 / 飞书 / 公众号后台。请先点确定保存，再让对方校验该 URL。')
      ).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: '复制' }));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(expectedUrl);
      expect(successSpy).toHaveBeenCalledWith('复制成功');
    });
    successSpy.mockRestore();
  });

  it('does not persist a channel until confirm', async () => {
    mockCreateSkillChannel.mockResolvedValue({
      id: 9,
      channel_type: 'platform',
      enabled: true,
      name: 'platform',
    });
    render(<SkillChannelPage />);

    await waitFor(() => {
      expect(screen.getByText('IT运维助手')).toBeTruthy();
    });

    fireEvent.click(screen.getAllByRole('button', { name: /添加渠道/ })[0]);
    await waitFor(() => {
      expect(screen.getByPlaceholderText('选填，便于识别不同入口')).toBeTruthy();
    });
    expect(mockCreateSkillChannel).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /确\s*定/ }));
    await waitFor(() => {
      expect(mockCreateSkillChannel).toHaveBeenCalledTimes(1);
    });
  });

  it('hides callback url when adding a non-IM channel', async () => {
    render(<SkillChannelPage />);

    await waitFor(() => {
      expect(screen.getByText('IT运维助手')).toBeTruthy();
    });

    fireEvent.click(screen.getAllByRole('button', { name: /添加渠道/ })[0]);
    await waitFor(() => {
      expect(screen.getByPlaceholderText('选填，便于识别不同入口')).toBeTruthy();
    });

    expect(screen.queryByText('回调地址')).toBeNull();
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

    const editButtons = screen.getAllByText('编辑');
    fireEvent.click(editButtons[1]); // 第二个是企微客服

    await waitFor(() => {
      const input = screen.getByDisplayValue('企微客服');
      expect(input).toBeTruthy();
    });
  });
});
