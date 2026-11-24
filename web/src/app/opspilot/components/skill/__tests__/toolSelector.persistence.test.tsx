import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ToolSelector from '../toolSelector';
import type { SelectTool } from '@/app/opspilot/types/tool';
import { skillToolUpdate } from '@/app/opspilot/utils/monitorToolConfig';

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string, fallback?: string) => fallback || key }) }));
const { fetchSkillTools } = vi.hoisted(() => ({
  fetchSkillTools: vi.fn(async () => [
    { id: 1, name: 'kubernetes', display_name: 'K8s', params: { kwargs: [{ key: 'kubernetes_instances', value: JSON.stringify([{ id: 'first', name: 'First', kubeconfig_data: 'first-config' }]) }] } },
    { id: 2, name: 'ssh', display_name: 'SSH', params: { kwargs: [] } },
    { id: 5, name: 'ticket', display_name: 'Ticket MCP', is_build_in: false, params: { kwargs: [] } },
  ]),
}));
vi.mock('@/app/opspilot/api/skill', () => ({ useSkillApi: () => ({ fetchSkillTools }) }));
vi.mock('../operateModal', () => ({ default: ({ visible, onOk }: { visible: boolean; onOk: (ids: number[]) => void }) => visible ? <>
  <button onClick={() => onOk([1, 2])}>select SSH</button>
  <button onClick={() => onOk([5])}>select MCP</button>
</> : null }));
vi.mock('@/components/operate-modal', () => ({ default: ({ visible, children, onOk }: { visible: boolean; children: React.ReactNode; onOk: () => void }) => visible ? <div>{children}<button onClick={onOk}>save config</button></div> : null }));
afterEach(cleanup);

function Editor({ initial, onChange }: { initial: SelectTool[]; onChange: (tools: SelectTool[]) => void }) {
  const [tools, setTools] = React.useState(initial);
  return <ToolSelector defaultTools={tools} onChange={next => { setTools(next); onChange(next); }} />;
}

it('preserves the newly saved Kubernetes instances when adding another tool', async () => {
  const onChange = vi.fn();
  const initial = [{ id: 1, name: 'K8s', rawName: 'kubernetes', kwargs: [{ key: 'kubernetes_instances', value: JSON.stringify([{ id: 'first', name: 'First', kubeconfig_data: 'first-config' }]) }] }];
  render(<Editor initial={initial} onChange={onChange} />);
  await screen.findByText('K8s');
  fireEvent.click(screen.getByText('skill.configureTool'));
  fireEvent.click(screen.getByRole('button', { name: /common.add/ }));
  fireEvent.change(screen.getByPlaceholderText('tool.kubernetes.kubeconfigDataPlaceholder'), { target: { value: 'second-config' } });
  fireEvent.click(screen.getByText('save config'));
  await waitFor(() => expect(JSON.parse(onChange.mock.lastCall![0][0].kwargs[0].value)).toHaveLength(2));
  fireEvent.click(screen.getByText('skill.addTool'));
  fireEvent.click(screen.getByText('select SSH'));
  const selected = onChange.mock.lastCall![0];
  expect(selected.map((tool: { rawName: string }) => tool.rawName)).toEqual(['kubernetes', 'ssh']);
  expect(JSON.parse(selected.find((tool: { rawName: string }) => tool.rawName === 'kubernetes').kwargs[0].value)).toHaveLength(2);
});

it.each(['kubernetes', 'kubernetes_data_collection'])('shows the saved %s binding on opening settings when only SSH is visible', async (name) => {
  fetchSkillTools.mockResolvedValueOnce([{ id: 2, name: 'ssh', display_name: 'SSH', params: { kwargs: [] } }]);
  const onChange = vi.fn();
  const initial = [{ id: 71, name, kwargs: [] }, { id: 2, name: 'ssh', kwargs: [] }];
  render(<Editor initial={initial} onChange={onChange} />);
  await screen.findByText('SSH');
  expect(screen.getByText(name)).toBeTruthy();
  expect(screen.getByText('当前目录不可见')).toBeTruthy();
  expect(onChange).not.toHaveBeenCalled();
});

it('keeps a saved binding when it is absent from the current catalog, including after adding a visible tool', async () => {
  const onChange = vi.fn();
  const initial = [{ id: 91, name: 'enterprise_connector', icon: 'gongju', kwargs: [{ key: 'profile', value: 'configured' }] }];
  render(<Editor initial={initial} onChange={onChange} />);
  fireEvent.click(screen.getByText('skill.addTool'));
  await screen.findByText('select SSH');
  expect(await screen.findByText('enterprise_connector')).toBeTruthy();
  expect(onChange).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('select SSH'));
  expect(onChange.mock.lastCall?.[0]).toEqual(expect.arrayContaining([expect.objectContaining(initial[0])]));
});

it('matches a name-only built-in and keeps an unavailable MCP across a picker change', async () => {
  const original: SelectTool[] = [
    { name: 'ssh', kwargs: [] },
    { id: 77, name: 'private_connector', isBuildIn: false, kwargs: [{ key: 'profile', value: 'saved' }] },
  ];
  const onChange = vi.fn();
  render(<Editor initial={original} onChange={onChange} />);
  await screen.findByText('SSH');
  expect(screen.getByText('private_connector')).toBeTruthy();
  expect(onChange).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('添加 MCP'));
  fireEvent.click(screen.getByText('select MCP'));
  const update = skillToolUpdate(onChange.mock.lastCall![0], original);
  expect(update.tools).toEqual([...original, { id: 5, name: 'ticket', icon: 'gongjuji', kwargs: [] }]);
});

it('removes exactly the chosen name-only binding and allows intentionally removing the last one', async () => {
  const original: SelectTool[] = [{ name: 'first' }, { name: 'last' }];
  const onChange = vi.fn();
  render(<Editor initial={original} onChange={onChange} />);
  await screen.findAllByText('当前目录不可见');
  fireEvent.click(screen.getByLabelText('删除 first'));
  expect(onChange.mock.lastCall![0]).toEqual([original[1]]);
  fireEvent.click(screen.getByLabelText('删除 last'));
  expect(skillToolUpdate(onChange.mock.lastCall![0], original)).toEqual({ tools: [] });
});

it('does not attach saved connection parameters to another tool now occupying its ID', async () => {
  const original: SelectTool[] = [{ id: 1, name: 'removed_connector', kwargs: [{ key: 'profile', value: 'old' }] }];
  const onChange = vi.fn();
  render(<Editor initial={original} onChange={onChange} />);
  await screen.findByText('当前目录不可见');
  fireEvent.click(screen.getByText('skill.addTool'));
  fireEvent.click(screen.getByText('select SSH'));
  expect(skillToolUpdate(onChange.mock.lastCall![0], original).tools).toEqual([
    original[0], { id: 2, name: 'ssh', icon: 'gongjuji', kwargs: [] },
  ]);
});

it('scrubs historical monitor credentials when an edit retains an unavailable monitor binding', async () => {
  const original = [{ id: -6, name: 'monitor', kwargs: [{ key: 'password', value: 'legacy-test-value' }] }];
  const onChange = vi.fn();
  render(<Editor initial={original} onChange={onChange} />);
  await screen.findByText('当前目录不可见');
  fireEvent.click(screen.getByText('skill.addTool'));
  fireEvent.click(screen.getByText('select SSH'));
  expect(onChange.mock.lastCall![0][0]).toEqual({ id: -6, name: 'monitor', kwargs: [] });
});
