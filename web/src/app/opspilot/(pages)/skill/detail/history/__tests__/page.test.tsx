import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SkillHistoryPage from '../page';
import AnalysisConfig from '../AnalysisConfig';
import zh from '@/app/opspilot/locales/zh.json';

const analysisApi = vi.hoisted(() => ({
  channels: vi.fn(), list: vi.fn(), create: vi.fn(), preview: vi.fn(), report: vi.fn(), retry: vi.fn(), pdf: vi.fn(),
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
      const types: Record<string, string> = zh.skill.channel.types;
      const text = entries[key.replace(/^skill\.analysis\./, '')] || types[key.replace(/^skill\.channel\.types\./, '')] || fallback || key;
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
    analysisApi.channels.mockResolvedValue([{ channel_type: 'platform', conversation_count: 2 },
      { channel_type: 'workflow', conversation_count: 1 }, { channel_type: 'workbench', conversation_count: 3 }]);
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

  it('shows both flow sources by name and keeps older conversations readable', async () => {
    mockFetchAdminSkillConversations.mockResolvedValue({ count: 3, items: [
      { session_id: 'a', channel_type: 'workflow', channel_name: '每日巡检', title: '巡检' },
      { session_id: 'b', channel_type: 'workbench', channel_name: '故障分析', title: '分析' },
      { session_id: 'c', channel_type: 'workflow', channel_name: '', title: '旧记录' },
    ] });
    render(<SkillHistoryPage />);
    await screen.findByText('编排中心 · 每日巡检');
    expect(screen.getByText('工作台 · 故障分析')).toBeTruthy();
    expect(within(screen.getByRole('row', { name: /旧记录/ })).getByText('编排中心')).toBeTruthy();
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
    expect(analysisApi.create).toHaveBeenCalledWith(expect.objectContaining({ scope: 'range', start: expect.any(String), end: expect.any(String), channel_types: ['platform'] }),
      expect.objectContaining({ objective: 'overview', name: expect.stringContaining('综合分析'), request_id: expect.any(String) }));
  });

  it('retains selected conversations across pages and blocks an empty preview', async () => {
    analysisApi.list.mockResolvedValue({ items: [], count: 0 });
    analysisApi.preview.mockImplementation(async scope => ({ conversation_count: 2, question_count: 2, issue: scope.scope === 'range' ? 'empty' : '' }));
    mockFetchAdminSkillConversations.mockImplementation(async ({ page = 1 }) => ({
      count: 6, items: [{ title: '对话' + page, session_id: 's' + page, person_display: '用户', channel_type: 'platform', channel_name: 'web' }],
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
    fireEvent.click(within(picker.getByRole('table')).getAllByRole('checkbox')[1]);
    fireEvent.click(picker.getByTitle('2'));
    await picker.findByText('对话2');
    fireEvent.click(within(picker.getByRole('table')).getAllByRole('checkbox')[1]);
    await picker.findByText('已选 2 个对话');
    await picker.findByText('覆盖 2 个对话、2 条用户提问');
    fireEvent.click(picker.getByRole('button', { name: '创建任务' }));
    await waitFor(() => expect(analysisApi.create).toHaveBeenCalledWith({ scope: 'sessions', session_ids: ['s1', 's2'] }, expect.any(Object)));
  });

  it('asks for an explicit choice when the range only contains workflows', async () => {
    analysisApi.channels.mockResolvedValue([{ channel_type: 'workflow', conversation_count: 3 }]);
    analysisApi.preview.mockResolvedValue({ conversation_count: 3, question_count: 4, issue: '' });
    render(<AnalysisConfig api={analysisApi} skillId="123" person="" onClose={vi.fn()} onCreated={vi.fn()} />);
    const flow = await screen.findByLabelText('编排中心（3 个对话）');
    const submit = screen.getByRole('button', { name: '创建任务' });
    expect(flow).toHaveProperty('checked', false);
    expect(screen.queryByRole('checkbox', { name: /平台/ })).toBeNull();
    expect(submit).toHaveProperty('disabled', true);
    expect(analysisApi.preview).not.toHaveBeenCalled();
    fireEvent.click(flow);
    expect(flow).toHaveProperty('checked', true);
    await waitFor(() => expect(analysisApi.preview).toHaveBeenCalledWith(expect.objectContaining({ channel_types: ['workflow'] })));
    await screen.findByText('覆盖 3 个对话、4 条用户提问');
    fireEvent.click(submit);
    await waitFor(() => expect(analysisApi.create).toHaveBeenCalledWith(expect.objectContaining({
      channel_types: ['workflow'],
    }), expect.any(Object)));
  });

  it('keeps an explicitly selected flow after hiding its type and allows removing it', async () => {
    analysisApi.preview.mockResolvedValue({ conversation_count: 1, question_count: 1, issue: '' });
    mockFetchAdminSkillConversations.mockImplementation(async ({ channel_types }) => {
      const includesFlow = channel_types?.split(',').includes('workflow');
      return { count: includesFlow ? 1 : 0, items: includesFlow ? [{
        session_id: 'flow-run', title: '巡检结果', channel_type: 'workflow', channel_name: '每日巡检', person_display: 'admin',
      }] : [] };
    });
    render(<AnalysisConfig api={analysisApi} skillId="123" person="" onClose={vi.fn()} onCreated={vi.fn()} />);
    fireEvent.click(screen.getByText('指定对话'));
    const flow = await screen.findByLabelText('编排中心（1 个对话）');
    expect(flow).toHaveProperty('checked', false);
    expect(screen.getByLabelText('工作台（3 个对话）')).toHaveProperty('checked', false);
    expect(screen.getByLabelText('平台（2 个对话）')).toHaveProperty('checked', true);
    await waitFor(() => expect(mockFetchAdminSkillConversations).toHaveBeenCalledWith(expect.objectContaining({ channel_types: 'platform' })));
    fireEvent.click(flow);
    await screen.findByText('编排中心 · 每日巡检');
    fireEvent.click(within(screen.getByRole('row', { name: /巡检结果/ })).getByRole('checkbox'));
    fireEvent.click(flow);
    await screen.findByText('覆盖 1 个对话、1 条用户提问');
    expect(analysisApi.preview).toHaveBeenCalledWith({ scope: 'sessions', session_ids: ['flow-run'] });
    expect(screen.queryByText('编排中心 · 每日巡检')).toBeNull();
    fireEvent.click(screen.getByText('已选 1 个对话'));
    fireEvent.click(screen.getByRole('button', { name: '移除对话「巡检结果」' }));
    expect(screen.getByRole('button', { name: '创建任务' })).toHaveProperty('disabled', true);
  });

  it('reopens a completed report, downloads its PDF and opens its cited message', async () => {
    const task = { id: 5, name: '连接质量', creator: 'alice', created_at: '2026-11-23', status: 'completed', objective: 'quality',
      scope: { scope: 'sessions', session_ids: ['s-1'], channel_types: ['workflow', 'workbench'] }, conversation_count: 1, question_count: 1 };
    analysisApi.list.mockResolvedValue({ items: [task], count: 1 });
    analysisApi.report.mockResolvedValue({ ...task, focus: '', findings: [{ finding: '回答缺少重试步骤', suggestion: '添加重试说明',
      evidence: [{ session_id: 's-1', message_id: 17 }] }] });
    const pdf = new Blob(['%PDF-'], { type: 'application/pdf' });
    analysisApi.pdf.mockResolvedValue(pdf);
    render(<SkillHistoryPage />);
    fireEvent.click(screen.getByText('智能分析'));
    fireEvent.click(await screen.findByText('查看报告'));
    expect(await screen.findByText('回答缺少重试步骤')).toBeTruthy();
    expect(screen.getByText('指定对话 · 编排中心 / 工作台')).toBeTruthy();
    fireEvent.click(screen.getByText('导出 PDF'));
    await waitFor(() => expect(savePdf).toHaveBeenCalledWith(pdf, '连接质量.pdf'));
    fireEvent.click(screen.getByText('查看原对话 #17'));
    await waitFor(() => expect(mockFetchAdminSkillSessionMessages).toHaveBeenCalledWith('s-1', 17));
    fireEvent.click(await screen.findByText('查看完整对话'));
    await waitFor(() => expect(mockFetchAdminSkillSessionMessages).toHaveBeenCalledWith('s-1'));
  });
});
