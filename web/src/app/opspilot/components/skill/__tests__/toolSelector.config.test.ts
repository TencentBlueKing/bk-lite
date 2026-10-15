import { describe, expect, it } from 'vitest';
import { toolHasConfigurableFields } from '../toolSelector';
import type { SelectTool } from '@/app/opspilot/types/tool';

const tool = (overrides: Partial<SelectTool>): SelectTool => ({
  id: 1,
  name: '日志中心',
  icon: 'gongju',
  ...overrides,
});

describe('toolHasConfigurableFields', () => {
  it('hides config when a tool or MCP has no parameters', () => {
    expect(toolHasConfigurableFields(tool({ kwargs: [] }))).toBe(false);
    expect(toolHasConfigurableFields(tool({ isBuildIn: false, kwargs: [] }))).toBe(false);
    expect(toolHasConfigurableFields(tool({ rawName: 'monitor', kwargs: [{ key: 'token', value: 'x' }] }))).toBe(false);
  });

  it('shows config when parameters or a connection form exist', () => {
    expect(toolHasConfigurableFields(tool({ kwargs: [{ key: 'host', value: '' }] }))).toBe(true);
    expect(toolHasConfigurableFields(tool({ rawName: 'redis', kwargs: [] }))).toBe(true);
    expect(toolHasConfigurableFields(tool({ rawName: 'kubernetes', kwargs: [] }))).toBe(true);
  });
});
