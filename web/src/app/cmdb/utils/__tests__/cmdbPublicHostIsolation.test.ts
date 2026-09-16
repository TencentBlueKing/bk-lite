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
    readSource('../../(pages)/assetData/detail/monitorPolicy/page.tsx'),
    readSource('../../(pages)/assetData/detail/nodeStatus/page.tsx'),
    readSource('../../(pages)/assetData/detail/relatedTopology/page.tsx'),
    readSource('../../(pages)/assetData/detail/networkStatusTopology/page.tsx'),
    readSource('../../(pages)/assetData/detail/application3D/page.tsx'),
    readSource('../../(pages)/assetData/detail/room3D/page.tsx'),
    readSource('../../(pages)/assetData/detail/relationships/page.tsx'),
    readSource(
      '../../(pages)/assetData/detail/relationships/publicRelatedTopoSlot.tsx',
    ),
    readSource(
      '../../(pages)/assetData/detail/relationships/publicNetworkStatusTopoSlot.tsx',
    ),
    readSource(
      '../../(pages)/assetData/detail/relationships/publicRoom3DSlot.tsx',
    ),
  ];

  it('does not statically import provider business implementations', () => {
    for (const source of hosts) {
      expect(source).not.toMatch(/from ['"]@\/app\/ops-analysis\/components/);
      expect(source).not.toMatch(/from ['"]@\/app\/monitor\/(pages|components)/);
      expect(source).not.toMatch(/from ['"]@\/app\/node-manager/);
      expect(source).not.toMatch(/from ['"]@\/app\/apm/);
      expect(source).not.toMatch(/from ['"]@\/app\/log/);
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
    const room3DSlotSource = readSource(
      '../../(pages)/assetData/detail/relationships/publicRoom3DSlot.tsx',
    );
    const relationshipsSource = readSource(
      '../../(pages)/assetData/detail/relationships/page.tsx',
    );
    const monitorPolicyPage = readSource(
      '../../(pages)/assetData/detail/monitorPolicy/page.tsx',
    );
    const nodeStatusPage = readSource(
      '../../(pages)/assetData/detail/nodeStatus/page.tsx',
    );
    expect(hookSource).toContain("useAppWidget('monitor.monitorView')");
    expect(hookSource).toContain("useAppWidget('monitor.monitorPolicy')");
    expect(hookSource).toContain("useAppWidget('node.nodeStatus')");
    expect(hookSource).toContain(
      "useAppWidget('ops-analysis.networkStatusTopology')",
    );
    expect(hookSource).not.toContain(
      "useAppWidget('ops-analysis.relatedTopology')",
    );
    expect(hookSource).toContain("useAppWidget('ops-analysis.room3D')");
    expect(pageSource).toContain('useAppWidget(widgetKey)');
    expect(pageSource).toContain('useLazyAppWidget');
    expect(pageSource).toContain('canUsePublic && Boolean(identifier)');
    expect(slotSource).toContain("useAppWidget('ops-analysis.relatedTopology')");
    expect(slotSource).toContain('useLazyAppWidget');
    expect(networkStatusSlotSource).toContain(
      "useAppWidget('ops-analysis.networkStatusTopology')",
    );
    expect(networkStatusSlotSource).toContain('useLazyAppWidget');
    expect(room3DSlotSource).toContain("useAppWidget('ops-analysis.room3D')");
    expect(room3DSlotSource).toContain('useLazyAppWidget');
    // 售卖门只由目录声明表达：OA 件在侧栏、Segmented 与槽里一律只看 declared，
    // 宿主不得再自行拿 clientData 判一次「已购运营分析」。
    for (const source of [
      hookSource,
      pageSource,
      slotSource,
      networkStatusSlotSource,
      room3DSlotSource,
      relationshipsSource,
    ]) {
      expect(source).not.toContain('hasAppAccess');
    }
    expect(room3DSlotSource).not.toContain('application3D');
    expect(monitorPolicyPage).toContain('widgetKey="monitor.monitorPolicy"');
    expect(monitorPolicyPage).toContain('identifierProp="monitorId"');
    expect(nodeStatusPage).toContain('widgetKey="node.nodeStatus"');
    expect(nodeStatusPage).toContain('identifierProp="nodeId"');
    expect(relationshipsSource).toContain('PublicRelatedTopoSlot');
    expect(relationshipsSource).toContain('PublicNetworkStatusTopoSlot');
    expect(relationshipsSource).toContain('PublicRoom3DSlot');
    expect(relationshipsSource).toContain("activeTab === 'topo'");
    expect(relationshipsSource).toContain("activeTab === 'network'");
    expect(relationshipsSource).toContain('<NetworkTopo');
    expect(relationshipsSource).toContain("value: 'networkStatusTopology'");
    expect(relationshipsSource).toContain("value: 'room3D'");
    expect(relationshipsSource).toContain(
      "showNetworkStatusTab && activeTab === 'networkStatusTopology'",
    );
    expect(relationshipsSource).toContain("value: 'serviceTree'");
    expect(relationshipsSource).toContain('<ServiceTree');
    expect(relationshipsSource).toContain("themes.includes('service_tree')");
    expect(relationshipsSource).toContain(
      "showRoom3DTab && activeTab === 'room3D'",
    );
    expect(relationshipsSource).not.toContain(
      "useAppWidget('ops-analysis.application3D')",
    );
    expect(relationshipsSource).toContain('normalizeRelationshipTab');
    expect(relationshipsSource).toContain('relationshipGatesSettled');
    expect(relationshipsSource).toContain('<Topo');
    expect(relationshipsSource).not.toMatch(/from ['"]@\/app\/ops-analysis/);
    expect(slotSource).not.toMatch(/from ['"]@\/app\/ops-analysis/);
    expect(networkStatusSlotSource).not.toMatch(/from ['"]@\/app\/ops-analysis/);
    expect(room3DSlotSource).not.toMatch(/from ['"]@\/app\/ops-analysis/);
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
    expect(sideMenuSource).toContain('relationshipTabForPublicMenuKey');
    expect(sideMenuSource).toContain(
      "buildRelationshipTabHref(",
    );
  });

  it('lands the room3D sidebar entry on the relationships tab like the room layout view', () => {
    const room3DPage = readSource(
      '../../(pages)/assetData/detail/room3D/page.tsx',
    );
    const sideMenuSource = readSource(
      '../../(pages)/assetData/components/sub-layout/side-menu.tsx',
    );
    expect(room3DPage).toContain('/cmdb/assetData/detail/relationships');
    expect(room3DPage).toContain("params.set('tab', 'room3D')");
    expect(room3DPage).toContain('router.replace');
    expect(room3DPage).not.toContain('CmdbPublicWidgetPage');
    expect(sideMenuSource).toContain('publicShortcutTabs');
  });
});
