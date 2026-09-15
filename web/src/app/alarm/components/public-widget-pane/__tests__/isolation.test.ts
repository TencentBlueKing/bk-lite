import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string) {
  return readFileSync(resolve(here, relativePath), 'utf8');
}

describe('alarm public widget host isolation', () => {
  const hosts = [
    readSource('../index.tsx'),
    readSource('../../../(pages)/alarms/components/alarmDetail.tsx'),
    readSource('../../alarm-detail-drawer/index.tsx'),
  ];

  it('does not statically import provider business modules', () => {
    for (const source of hosts) {
      expect(source).not.toMatch(/from ['"]@\/app\/ops-analysis/);
      expect(source).not.toMatch(/from ['"]@\/app\/monitor/);
      expect(source).not.toMatch(/from ['"]@\/app\/cmdb/);
      expect(source).not.toContain('operation_analysis');
    }
  });

  it('loads widgets through the shared capability seam', () => {
    const paneSource = readSource('../index.tsx');
    expect(paneSource).toContain("useAppWidget('monitor.monitorView')");
    expect(paneSource).toContain("useAppWidget('ops-analysis.relatedTopology')");
    expect(paneSource).toContain("useAppWidget('cmdb.baseInfo')");
    expect(paneSource).toContain("hasAppAccess(clientData, 'ops-analysis')");
    expect(paneSource).toContain('resolveAlarmPublicWidgetVisibility');
    expect(paneSource).toContain('useLazyAppWidget');
    expect(paneSource).toContain('active && Boolean(identifier)');
    expect(paneSource).toContain('useActiveBoundIdentifier');
    expect(paneSource).toContain('toolbarStart');
    expect(paneSource).not.toContain("t('common.refresh')");
    expect(paneSource).not.toContain('ReloadOutlined');
    expect(paneSource).not.toContain('520px');
  });

  it('keeps object switching on the detail shell, not inside a public tab', () => {
    const paneSource = readSource('../index.tsx');
    const pageSource = readSource(
      '../../../(pages)/alarms/components/alarmDetail.tsx',
    );
    const drawerSource = readSource('../../alarm-detail-drawer/index.tsx');
    expect(paneSource).toContain('AlarmObjectSwitcher');
    expect(pageSource).toContain('AlarmObjectSwitcher');
    expect(drawerSource).toContain('AlarmObjectSwitcher');
    expect(pageSource).toContain('toolbarStart={renderObjectSwitcher()}');
    expect(drawerSource).toContain('toolbarStart={renderObjectSwitcher()}');
    expect(pageSource).not.toContain('mb-3 shrink-0');
    expect(drawerSource).not.toContain('mb-3 shrink-0');
    expect(paneSource).not.toContain('centers.length > 1');
    expect(pageSource).not.toContain('centers.length > 1');
    expect(drawerSource).not.toContain('centers.length > 1');
  });

  it('keeps inactive public tabs mounted without importing until first activation', () => {
    const pageSource = readSource(
      '../../../(pages)/alarms/components/alarmDetail.tsx',
    );
    const drawerSource = readSource('../../alarm-detail-drawer/index.tsx');
    expect(pageSource).toContain(
      "activeTab === 'monitorView'\n                  ? 'flex min-h-0 flex-1 flex-col overflow-hidden'\n                  : 'hidden'",
    );
    expect(drawerSource).toContain(
      "activeTab === 'relatedTopology'\n                  ? 'flex min-h-0 flex-1 flex-col overflow-hidden'\n                  : 'hidden'",
    );
  });
});
