import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ToolSelector from '../toolSelector';

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string, fallback?: string) => fallback || key }) }));
vi.mock('@/app/opspilot/api/skill', () => ({
  useSkillApi: () => ({ fetchSkillTools: async () => [
    { id: 1, name: 'kubernetes', display_name: 'K8s', params: { kwargs: [{ key: 'kubernetes_instances', value: JSON.stringify([{ id: 'first', name: 'First', kubeconfig_data: 'first-config' }]) }] } },
    { id: 2, name: 'ssh', display_name: 'SSH', params: { kwargs: [] } },
  ] }),
}));
vi.mock('../operateModal', () => ({ default: ({ visible, onOk }: { visible: boolean; onOk: (ids: number[]) => void }) => visible ? <button onClick={() => onOk([1, 2])}>select SSH</button> : null }));
vi.mock('@/components/operate-modal', () => ({ default: ({ visible, children, onOk }: { visible: boolean; children: React.ReactNode; onOk: () => void }) => visible ? <div>{children}<button onClick={onOk}>save config</button></div> : null }));
afterEach(cleanup);

it('preserves the newly saved Kubernetes instances when adding another tool', async () => {
  const onChange = vi.fn();
  const initial = [{ id: 1, name: 'K8s', rawName: 'kubernetes', kwargs: [{ key: 'kubernetes_instances', value: JSON.stringify([{ id: 'first', name: 'First', kubeconfig_data: 'first-config' }]) }] }];
  render(<ToolSelector defaultTools={initial} onChange={onChange} />);
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
