import { describe, expect, it } from 'vitest';
import {
  skillDebugDistributeSessionId,
  skillSelectionEnablesJobDistribute,
} from '../jobDistributeEntry';

describe('job distribute entry', () => {
  it('shows the entry when the selected tool is job management', () => {
    expect(skillSelectionEnablesJobDistribute([
      { name: '作业管理', rawName: 'job_mgmt' },
    ])).toBe(true);
    expect(skillSelectionEnablesJobDistribute([
      { name: 'job_mgmt' },
    ])).toBe(true);
  });

  it('hides the entry when job management is not selected', () => {
    expect(skillSelectionEnablesJobDistribute([
      { name: '作业管理' },
      { name: '监控', rawName: 'monitor' },
    ])).toBe(false);
    expect(skillSelectionEnablesJobDistribute([])).toBe(false);
  });

  it('uses the debug thread key as the staged file session', () => {
    expect(skillDebugDistributeSessionId('abc')).toBe('thread:abc');
    expect(skillDebugDistributeSessionId('  ')).toBe('');
  });
});
