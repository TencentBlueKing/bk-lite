import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string) {
  return readFileSync(resolve(here, relativePath), 'utf8');
}

describe('CMDB public widget host isolation', () => {
  const hosts = [
    readSource('../../(pages)/assetData/components/sub-layout/side-menu.tsx'),
    readSource('../../hooks/useCmdbPublicMenuItems.ts'),
    readSource('../../components/public/CmdbPublicWidgetPage.tsx'),
    readSource('../../(pages)/assetData/detail/monitorView/page.tsx'),
    readSource('../../(pages)/assetData/detail/alertList/page.tsx'),
    readSource('../../(pages)/assetData/detail/relatedTopology/page.tsx'),
    readSource('../../(pages)/assetData/detail/networkStatusTopology/page.tsx'),
    readSource('../../(pages)/assetData/detail/application3D/page.tsx'),
    readSource('../../(pages)/assetData/detail/relationships/page.tsx'),
    readSource(
      '../../(pages)/assetData/detail/relationships/publicRelatedTopoSlot.tsx',
    ),
    readSource(
      '../../(pages)/assetData/detail/relationships/publicNetworkStatusTopoSlot.tsx',
    ),
  ];

  it('does not statically import provider business implementations', () => {
    for (const source of hosts) {
      expect(source).not.toMatch(/from ['"]@\/app\/ops-analysis\/components/);
      expect(source).not.toMatch(/from ['"]@\/app\/monitor\/(pages|components)/);
      expect(source).not.toContain('operation_analysis');
    }
  });

  it('probes and loads widgets through the shared capability seam', () => {
    const hookSource = readSource('../../hooks/useCmdbPublicMenuItems.ts');
    const pageSource = readSource(
      '../../components/public/CmdbPublicWidgetPage.tsx',
    );
    const slotSource = readSource(
      '../../(pages)/assetData/detail/relationships/publicRelatedTopoSlot.tsx',
    );
    const networkStatusSlotSource = readSource(
      '../../(pages)/assetData/detail/relationships/publicNetworkStatusTopoSlot.tsx',
    );
    const relationshipsSource = readSource(
      '../../(pages)/assetData/detail/relationships/page.tsx',
    );
    expect(hookSource).toContain("useAppWidget('monitor.monitorView')");
    expect(hookSource).toContain("hasAppAccess(clientData, 'ops-analysis')");
    expect(hookSource).toContain(
      "useAppWidget('ops-analysis.networkStatusTopology')",
    );
    expect(hookSource).not.toContain(
      "useAppWidget('ops-analysis.relatedTopology')",
    );
    expect(pageSource).toContain('useAppWidget(widgetKey)');
    expect(pageSource).toContain('useLazyAppWidget');
    expect(pageSource).toContain('canShowCrossModulePublicWidget');
    expect(pageSource).toContain("hasAppAccess(clientData, 'ops-analysis')");
    expect(pageSource).toContain('canUsePublic && Boolean(identifier)');
    expect(slotSource).toContain("useAppWidget('ops-analysis.relatedTopology')");
    expect(slotSource).toContain('useLazyAppWidget');
    expect(networkStatusSlotSource).toContain(
      "useAppWidget('ops-analysis.networkStatusTopology')",
    );
    expect(networkStatusSlotSource).toContain('useLazyAppWidget');
    expect(relationshipsSource).toContain('PublicRelatedTopoSlot');
    expect(relationshipsSource).toContain('PublicNetworkStatusTopoSlot');
    expect(relationshipsSource).toContain("activeTab === 'topo'");
    expect(relationshipsSource).toContain("activeTab === 'network'");
    expect(relationshipsSource).toContain('<NetworkTopo');
    expect(relationshipsSource).toContain("value: 'networkStatusTopology'");
    expect(relationshipsSource).toContain(
      "showNetworkStatusTab && activeTab === 'networkStatusTopology'",
    );
    expect(relationshipsSource).toContain('normalizeRelationshipTab');
    expect(relationshipsSource).toContain('relationshipGatesSettled');
    expect(relationshipsSource).toContain('<Topo');
    expect(relationshipsSource).not.toMatch(/from ['"]@\/app\/ops-analysis/);
    expect(slotSource).not.toMatch(/from ['"]@\/app\/ops-analysis/);
    expect(networkStatusSlotSource).not.toMatch(/from ['"]@\/app\/ops-analysis/);
  });

  it('keeps the relatedTopology route as a query-preserving redirect onto topo', () => {
    const redirectSource = readSource(
      '../../(pages)/assetData/detail/relatedTopology/page.tsx',
    );
    const networkStatusPage = readSource(
      '../../(pages)/assetData/detail/networkStatusTopology/page.tsx',
    );
    const sideMenuSource = readSource(
      '../../(pages)/assetData/components/sub-layout/side-menu.tsx',
    );
    expect(redirectSource).toContain('/cmdb/assetData/detail/relationships');
    expect(redirectSource).toContain("params.set('tab', 'topo')");
    expect(redirectSource).toContain('router.replace');
    expect(redirectSource).not.toContain('CmdbPublicWidgetPage');
    expect(networkStatusPage).toContain('/cmdb/assetData/detail/relationships');
    expect(networkStatusPage).toContain(
      "params.set('tab', 'networkStatusTopology')",
    );
    expect(networkStatusPage).toContain('router.replace');
    expect(networkStatusPage).not.toContain('CmdbPublicWidgetPage');
    expect(sideMenuSource).toContain(
      "item.key === 'networkStatusTopology'",
    );
    expect(sideMenuSource).toContain(
      "buildRelationshipTabHref(",
    );
  });
});
