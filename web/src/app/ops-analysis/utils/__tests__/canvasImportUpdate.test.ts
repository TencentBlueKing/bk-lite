import { describe, expect, it } from 'vitest';

import { canvasImportUpdatePath, canvasSelectionAfterImportUpdate } from '../canvasImportUpdate';
import type { DirItem } from '@/app/ops-analysis/types';

describe('canvas import update path', () => {
  it('binds every canvas type to its own id', () => {
    expect(canvasImportUpdatePath('dashboard', 9)).toBe(
      '/operation_analysis/api/dashboard/9/import-update/',
    );
    expect(canvasImportUpdatePath('topology', 9)).toBe(
      '/operation_analysis/api/topology/9/import-update/',
    );
    expect(canvasImportUpdatePath('architecture', 9)).toBe(
      '/operation_analysis/api/architecture/9/import-update/',
    );
    expect(canvasImportUpdatePath('screen', 9)).toBe(
      '/operation_analysis/api/screen/9/import-update/',
    );
    expect(canvasImportUpdatePath('report', 9)).toBe(
      '/operation_analysis/api/report/9/import-update/',
    );
    expect(canvasImportUpdatePath('networkTopology', 9)).toBe(
      '/operation_analysis/api/network_topology/9/import-update/',
    );
  });

  it('replaces the open canvas name and desc from the import response', () => {
    const current: DirItem = {
      id: 'dashboard_9',
      data_id: '9',
      name: '旧标题',
      desc: '旧描述',
      type: 'dashboard',
      groups: [4, 5],
    };

    expect(
      canvasSelectionAfterImportUpdate(current, {
        name: '新标题',
        desc: '新描述',
      }),
    ).toEqual({
      ...current,
      name: '新标题',
      desc: '新描述',
    });
  });
});
