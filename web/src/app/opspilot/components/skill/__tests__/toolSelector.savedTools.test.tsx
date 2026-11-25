import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ToolSelector from '../toolSelector';

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string, fallback?: string) => fallback || key }) }));
vi.mock('@/app/opspilot/api/skill', () => ({
  useSkillApi: () => ({ fetchSkillTools: async () => [
    { id: 2, name: 'ssh', display_name: 'SSH', params: { kwargs: [] } },
  ] }),
}));
vi.mock('../operateModal', () => ({ default: () => null }));
vi.mock('@/components/operate-modal', () => ({ default: () => null }));
afterEach(cleanup);

it('keeps a saved builtin tool and drops an MCP missing from the catalog', async () => {
  const onChange = vi.fn();
  render(<ToolSelector defaultTools={[
    { id: 9, name: '告警中心', rawName: 'alerts', isBuildIn: true, kwargs: [] },
    { id: 8, name: '私有 MCP', rawName: 'private-mcp', isBuildIn: false, kwargs: [] },
  ]} onChange={onChange} />);
  await waitFor(() => expect(onChange).toHaveBeenCalled());
  const selected = onChange.mock.lastCall![0] as { id: number }[];
  expect(selected.map((tool) => tool.id)).toContain(9);
  expect(selected.map((tool) => tool.id)).not.toContain(8);
});
