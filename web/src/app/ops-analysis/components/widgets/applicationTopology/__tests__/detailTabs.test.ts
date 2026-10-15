import { describe, expect, it } from 'vitest';
import { resolveApplicationTopologyDetailTabs } from '../detailPanel';

describe('application topology detail tabs', () => {
  it('hides a tab when that module is not declared', () => {
    expect(resolveApplicationTopologyDetailTabs({
      shareMode: false,
      baseInfoDeclared: true,
      monitorViewDeclared: false,
      alertListDeclared: true,
    })).toEqual(['cmdb', 'alerts']);
  });

  it('opens no module tabs in share mode', () => {
    expect(resolveApplicationTopologyDetailTabs({
      shareMode: true,
      baseInfoDeclared: true,
      monitorViewDeclared: true,
      alertListDeclared: true,
    })).toEqual([]);
  });
});
