import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import SkillTemplatesPage from '../page';

const api = vi.hoisted(() => ({
  fetchSkillTemplates: vi.fn(), fetchSkill: vi.fn(), fetchSkillTools: vi.fn(), createSkill: vi.fn(),
}));
const push = vi.hoisted(() => vi.fn());
let canCreate = true;
vi.mock('@/app/opspilot/api/skill', () => ({ useSkillApi: () => api }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/hooks/usePermissions', () => ({ default: () => ({ hasPermission: () => canCreate }) }));
vi.mock('@/components/permission', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }));

const assistant = {
  id: 1, name: 'AI智能助手', introduction: '平台运维助手', skill_type: 3, skill_prompt: '当前环境的提示词',
  guide: '您好', enable_conversation_history: true, conversation_window_size: 9, run_model_call_limit: 18,
  temperature: 0.4, show_think: true, enable_suggest: false, enable_query_rewrite: false,
  force_wiki_grounded: true, allow_wiki_material_write: false, memory_write_rounds: 8,
  tools: [{ name: 'python', id: 999, kwargs: [{ key: 'token', value: 'old-secret' }] }],
  llm_model: 900, team: [99], memory_space: 70, wiki_knowledge_bases: [8], is_template: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  canCreate = true;
  window.matchMedia = vi.fn().mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() }));
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  api.fetchSkillTemplates.mockResolvedValue([assistant, { id: 2, name: 'Kubernetes 助手', introduction: '容器巡检', skill_type: 3 }]);
  api.fetchSkill.mockResolvedValue({ count: 1, items: [{ name: 'AI智能助手' }] });
  api.fetchSkillTools.mockResolvedValue([{ id: 23, name: 'python', icon: 'python' }]);
  api.createSkill.mockResolvedValue({ id: 100, name: 'AI智能助手 副本', introduction: '平台运维助手' });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('shows searchable templates and creates a separate agent using portable settings and local tools', async () => {
  render(<SkillTemplatesPage />);
  await screen.findByText('AI智能助手');
  fireEvent.change(screen.getByLabelText('skill.searchTemplates'), { target: { value: '平台运维' } });
  expect(screen.queryByText('Kubernetes 助手')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'skill.useTemp' }));
  await waitFor(() => expect(push).toHaveBeenCalledOnce());
  expect(api.createSkill).toHaveBeenCalledWith({
    name: 'AI智能助手 副本', introduction: '平台运维助手', skill_type: 3, skill_prompt: '当前环境的提示词',
    guide: '您好', enable_conversation_history: true, conversation_window_size: 9, run_model_call_limit: 18,
    temperature: 0.4, show_think: true, enable_suggest: false, enable_query_rewrite: false,
    force_wiki_grounded: true, allow_wiki_material_write: false, memory_write_rounds: 8,
    tools: [{ id: 23, name: 'python', icon: 'python', kwargs: [] }],
  });
  expect(push.mock.calls[0][0]).toMatch(/^\/opspilot\/skill\/detail\/settings\?id=100&/);
  expect(api.fetchSkillTemplates).toHaveBeenCalledOnce();
});

it('offers retry after a catalog loading failure', async () => {
  api.fetchSkillTemplates.mockRejectedValueOnce(new Error('offline'));
  render(<SkillTemplatesPage />);
  await screen.findByText('skill.templatesLoadFailed');
  fireEvent.click(screen.getByRole('button', { name: 'common.retry' }));
  await screen.findByText('AI智能助手');
  expect(api.fetchSkillTemplates).toHaveBeenCalledTimes(2);
});

it('does not create an agent without Add permission', async () => {
  canCreate = false;
  render(<SkillTemplatesPage />);
  await screen.findByText('AI智能助手');
  for (const button of screen.getAllByRole('button', { name: 'skill.useTemp' })) {
    expect(button.hasAttribute('disabled')).toBe(true);
    fireEvent.click(button);
  }
  expect(api.createSkill).not.toHaveBeenCalled();
});

it('keeps templates available for retry after creation fails', async () => {
  api.createSkill.mockRejectedValueOnce(new Error('offline'));
  render(<SkillTemplatesPage />);
  const name = await screen.findByText('AI智能助手');
  const card = name.closest('article');
  if (!card) throw new Error('template card missing');
  const button = within(card).getByRole('button', { name: 'skill.useTemp' });
  fireEvent.click(button);
  await waitFor(() => expect(api.createSkill).toHaveBeenCalledOnce());
  await waitFor(() => expect(button.hasAttribute('disabled')).toBe(false));
  await waitFor(() => expect(button.classList.contains('ant-btn-loading')).toBe(false));
  expect(push).not.toHaveBeenCalled();
  fireEvent.click(button);
  await waitFor(() => expect(push).toHaveBeenCalledOnce());
});


it('shows a local template switcher and navigates back to the agent list', async () => {
  render(<SkillTemplatesPage />);
  await screen.findByText('AI智能助手');
  expect(screen.getByRole('radio', { name: 'skill.templatesTitle' }).hasAttribute('checked')).toBe(true);
  fireEvent.click(screen.getByRole('radio', { name: 'skill.pageTitle' }));
  expect(push).toHaveBeenCalledWith('/opspilot/skill');
});
