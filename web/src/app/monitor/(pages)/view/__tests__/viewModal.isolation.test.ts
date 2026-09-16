import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string) {
  return readFileSync(resolve(here, relativePath), 'utf8');
}

describe('viewModal public widget host isolation', () => {
  const source = readSource('../viewModal.tsx');

  it('does not statically import provider business implementations', () => {
    expect(source).not.toMatch(/from ['"]@\/app\/ops-analysis/);
    expect(source).not.toMatch(/from ['"]@\/app\/cmdb/);
    expect(source).not.toMatch(/from ['"]@\/app\/log/);
    expect(source).not.toMatch(/from ['"]@\/app\/apm/);
    expect(source).not.toMatch(/from ['"]@\/app\/node-manager/);
  });

  it('probes public tabs through the shared capability seam', () => {
    expect(source).toContain("useAppWidget('ops-analysis.relatedTopology')");
    expect(source).toContain("useAppWidget('cmdb.baseInfo')");
    expect(source).toContain("useAppWidget('cmdb.assetChange')");
    expect(source).toContain("useAppWidget('node.nodeStatus')");
    // 公开 Tab 的售卖门只由 declared 表达，宿主不再自判「已购运营分析」。
    expect(source).not.toContain('hasAppAccess');
    expect(source).toContain('ViewModalPublicPane');
    expect(source).toContain('shouldLookupViewModalStableIds');
    expect(source).toContain("currentTab === 'monitorPolicy'");
    expect(source).not.toContain('monitor.monitorPolicy');
    expect(source).not.toContain('/monitor/view/detail/');
  });

  it('gives the drawer body a flex column so public tabs can fill remaining height', () => {
    expect(source).toContain("body: 'flex min-h-0 flex-col overflow-hidden'");
    expect(source).toContain("className=\"shrink-0\"");
    expect(source).toContain(
      'flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden',
    );
  });
});

describe('viewModal public pane height and toolbar', () => {
  const paneSource = readSource(
    '../../../components/public/ViewModalPublicPane.tsx',
  );

  it('fills the host tab and forwards embed toolbar callbacks instead of string-only props', () => {
    expect(paneSource).toContain('h-full');
    expect(paneSource).toContain('flex-1');
    expect(paneSource).toContain('min-h-0');
    expect(paneSource).toContain('onHeaderAction');
    expect(paneSource).toContain('onEmbedToolbar');
    expect(paneSource).toContain('onHeaderAction={setHeaderAction}');
    expect(paneSource).toContain('onEmbedToolbar={setEmbedToolbar}');
    expect(paneSource).not.toContain(
      'Widget as React.ComponentType<Record<string, string>>',
    );
  });
});
