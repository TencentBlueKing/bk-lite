import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import SkillSettingsPage from '../page';
import GenericModifyModal from '@/app/opspilot/components/generic-modify-modal';

const saveSkillDetail = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams('id=17') }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/context/userInfo', () => ({ useUserInfoContext: () => ({ selectedGroup: { id: 1 } }) }));
vi.mock('@/components/permission', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock('@/app/opspilot/components/custom-chat-sse', () => ({ default: () => null }));
vi.mock('@/app/opspilot/context/skillContext', () => ({ useSkill: () => ({ refreshSkillInfo: vi.fn() }) }));
vi.mock('@/app/opspilot/api/wiki', () => ({ useWikiApi: () => ({ fetchKnowledgeBases: async () => [] }) }));
vi.mock('@/app/opspilot/api/memory', () => ({ useMemoryApi: () => ({ fetchWorkflowMemorySpaces: async () => [] }) }));
vi.mock('@/app/opspilot/api/skill', () => ({
  useSkillApi: () => ({
    fetchSkillDetail: async () => ({
      name: '巡检助手', introduction: '集群巡检', team: [1], usage_team: [1], llm_model: 4,
      tools: [{ id: 7, name: 'kubernetes', kwargs: [{ key: 'kubernetes_instances', value: 'saved-clusters' }] }],
    }),
    fetchSkillTools: async () => [{ id: 8, name: 'ssh', params: { kwargs: [] } }],
    fetchLlmModels: async () => [],
    fetchSkillPackages: async () => ({ items: [], count: 0 }),
    saveSkillDetail,
  }),
}));
vi.mock('@/components/group-tree-select', () => ({
  default: ({ id, value, onChange }: { id: string; value?: number[]; onChange: (ids: number[]) => void }) => (
    <input id={id} value={value?.join(',') || ''} onChange={event => onChange(event.target.value.split(',').map(Number))} />
  ),
}));

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation(() => ({
    matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(),
  }));
});
afterEach(cleanup);

it('saves added management and usage organizations without submitting the unavailable Kubernetes binding', async () => {
  render(<SkillSettingsPage />);
  await screen.findByDisplayValue('巡检助手');
  fireEvent.change(screen.getByLabelText('skill.form.manageGroup'), { target: { value: '1,2' } });
  fireEvent.change(screen.getByLabelText(/skill.form.usageGroup/), { target: { value: '1,2,3' } });
  fireEvent.click(screen.getByRole('button', { name: 'common.save' }));
  await waitFor(() => expect(saveSkillDetail).toHaveBeenCalledOnce());
  const [id, payload] = saveSkillDetail.mock.calls[0];
  expect(id).toBe('17');
  expect(payload).toMatchObject({ team: [1, 2], usage_team: [1, 2, 3] });
  expect(payload).not.toHaveProperty('tools');
});

it('omits tools from the list edit dialog even when its initial row contains tools', async () => {
  const confirm = vi.fn();
  render(<GenericModifyModal visible formType="skill" onConfirm={confirm} onCancel={vi.fn()} initialValues={{
    id: 17, name: '巡检助手', introduction: '集群巡检', team: [1], usage_team: [1], tools: [],
  }} />);
  await screen.findByDisplayValue('巡检助手');
  fireEvent.change(screen.getByLabelText('skill.form.manageGroup'), { target: { value: '1,2' } });
  fireEvent.change(screen.getByLabelText(/skill.form.usageGroup/), { target: { value: '1,2,3' } });
  fireEvent.click(screen.getByRole('button', { name: 'common.confirm' }));
  await waitFor(() => expect(confirm).toHaveBeenCalledOnce());
  expect(confirm.mock.calls[0][0]).toMatchObject({ team: [1, 2], usage_team: [1, 2, 3] });
  expect(confirm.mock.calls[0][0]).not.toHaveProperty('tools');
});
