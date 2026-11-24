import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SkillHistoryPage from '../page';
import zh from '@/app/opspilot/locales/zh.json';

const analysisApi = vi.hoisted(() => ({
  list: vi.fn(), create: vi.fn(), preview: vi.fn(), report: vi.fn(), retry: vi.fn(), pdf: vi.fn(),
}));
const savePdf = vi.hoisted(() => vi.fn());
vi.mock('@/app/opspilot/api/historyAnalysis', () => ({ useHistoryAnalysisApi: () => analysisApi }));
vi.mock('file-saver', () => ({ saveAs: savePdf }));

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
    t: (key: string, fallback?: string, values: Record<string, string | number> = {}) => {
      const entries: Record<string, string> = zh.skill.analysis;
      const text = key.startsWith('skill.analysis.') ? entries[key.slice('skill.analysis.'.length)] : fallback || key;
      return text.replace(/\{(\w+)\}/g, (_, name: string) => String(values[name]));
    },
  }),
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({
    convertToLocalizedTime: (value: string) => value, timeZone: 'Asia/Shanghai',
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

  it('requires a preview and submits the selected time range once', async () => {
    analysisApi.list.mockResolvedValue({ items: [], count: 0 });
    analysisApi.preview.mockResolvedValue({ conversation_count: 2, question_count: 4, issue: '' });
    analysisApi.create.mockResolvedValue({ id: 5 });
    render(<SkillHistoryPage />);
    fireEvent.click(screen.getByText('智能分析'));
    fireEvent.click(await screen.findByText('新建分析'));
    const submit = screen.getByRole('button', { name: '创建任务' });
    expect(submit).toHaveProperty('disabled', true);
    await screen.findByText('覆盖 2 个对话、4 条用户提问');
    fireEvent.click(submit);
    fireEvent.click(submit);
    await waitFor(() => expect(analysisApi.create).toHaveBeenCalledTimes(1));
    expect(analysisApi.create).toHaveBeenCalledWith(expect.objectContaining({ scope: 'range', start: expect.any(String), end: expect.any(String) }),
      expect.objectContaining({ objective: 'overview', name: expect.stringContaining('综合分析'), request_id: expect.any(String) }));
  });

  it('retains selected conversations across pages and blocks an empty preview', async () => {
    analysisApi.list.mockResolvedValue({ items: [], count: 0 });
    analysisApi.preview.mockImplementation(async scope => ({ conversation_count: 2, question_count: 2, issue: scope.scope === 'range' ? 'empty' : '' }));
    mockFetchAdminSkillConversations.mockImplementation(async ({ page = 1 }) => ({
      count: 6, items: [{ title: '对话' + page, session_id: 's' + page, person_display: '用户', channel_name: 'web' }],
    }));
    render(<SkillHistoryPage />);
    fireEvent.click(screen.getByText('智能分析'));
    fireEvent.click(await screen.findByText('新建分析'));
    await screen.findByText('范围内没有用户提问，请调整范围。');
    expect(screen.getByRole('button', { name: '创建任务' })).toHaveProperty('disabled', true);
    fireEvent.click(screen.getByText('指定对话'));
    const modal = screen.getAllByRole('dialog').at(-1);
    if (!modal) throw Error('Missing configuration dialog');
    const picker = within(modal);
    await picker.findByText('对话1');
    fireEvent.click(picker.getAllByRole('checkbox')[1]);
    fireEvent.click(picker.getByTitle('2'));
    await picker.findByText('对话2');
    fireEvent.click(picker.getAllByRole('checkbox')[1]);
    await picker.findByText('已选 2 个对话');
    await picker.findByText('覆盖 2 个对话、2 条用户提问');
    fireEvent.click(picker.getByRole('button', { name: '创建任务' }));
    await waitFor(() => expect(analysisApi.create).toHaveBeenCalledWith({ scope: 'sessions', session_ids: ['s1', 's2'] }, expect.any(Object)));
  });

  it('reopens a completed report, downloads its PDF and opens its cited message', async () => {
    const task = { id: 5, name: '连接质量', creator: 'alice', created_at: '2026-11-23', status: 'completed', objective: 'quality',
      scope: { scope: 'sessions', session_ids: ['s-1'] }, conversation_count: 1, question_count: 1 };
    analysisApi.list.mockResolvedValue({ items: [task], count: 1 });
    analysisApi.report.mockResolvedValue({ ...task, focus: '', findings: [{ finding: '回答缺少重试步骤', suggestion: '添加重试说明',
      evidence: [{ session_id: 's-1', message_id: 17 }] }] });
    const pdf = new Blob(['%PDF-'], { type: 'application/pdf' });
    analysisApi.pdf.mockResolvedValue(pdf);
    render(<SkillHistoryPage />);
    fireEvent.click(screen.getByText('智能分析'));
    fireEvent.click(await screen.findByText('查看报告'));
    expect(await screen.findByText('回答缺少重试步骤')).toBeTruthy();
    fireEvent.click(screen.getByText('导出 PDF'));
    await waitFor(() => expect(savePdf).toHaveBeenCalledWith(pdf, '连接质量.pdf'));
    fireEvent.click(screen.getByText('查看原对话 #17'));
    await waitFor(() => expect(mockFetchAdminSkillSessionMessages).toHaveBeenCalledWith('s-1', 17));
    fireEvent.click(await screen.findByText('查看完整对话'));
    await waitFor(() => expect(mockFetchAdminSkillSessionMessages).toHaveBeenCalledWith('s-1'));
  });
});
