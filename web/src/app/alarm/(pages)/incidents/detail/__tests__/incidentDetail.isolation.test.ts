import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string) {
  return readFileSync(resolve(here, relativePath), 'utf8');
}

describe('incident detail public widget host isolation', () => {
  const pageSource = readSource('../page.tsx');
  const helperSource = readSource('../incidentPublicAssetChange.ts');

  it('does not statically import provider business implementations', () => {
    expect(pageSource).not.toMatch(/from ['"]@\/app\/cmdb/);
    expect(pageSource).not.toMatch(/from ['"]@\/app\/ops-analysis/);
    expect(pageSource).not.toMatch(/from ['"]@\/app\/monitor/);
    expect(pageSource).not.toContain('operation_analysis');
    expect(helperSource).not.toMatch(/from ['"]@\/app\/cmdb/);
  });

  it('loads asset change through the shared capability seam and one instUuid at a time', () => {
    expect(pageSource).toContain("useAppWidget('cmdb.assetChange')");
    // CMDB 提供的件挂到事故页不收「已购运营分析」的税：入口只看 declared + instUuid。
    expect(pageSource).not.toContain('hasAppAccess');
    expect(helperSource).not.toContain('hasOpsAnalysis');
    expect(pageSource).toContain('PublicWidgetPane');
    expect(pageSource).toContain('listIncidentAssetOptions');
    expect(pageSource).toContain('identifierProp="instUuid"');
    expect(pageSource).toContain('identifier={currentAssetUuid}');
    expect(pageSource).not.toContain('identifier={instUuids}');
    expect(pageSource).toContain("tab={t('alarms.assetChange')}");
    expect(pageSource).toContain('key="assetChange"');
    expect(pageSource).toContain('key="alert"');
  });

  it('renders a host switcher when there are multiple instUuids and may default to the first', () => {
    expect(pageSource).toContain('instUuids.length > 1');
    expect(pageSource).toContain('<Select');
    expect(pageSource).toContain('value={currentAssetUuid}');
    expect(helperSource).toContain('return instUuids[0] || \'\'');
  });

  it('labels switcher options from the snapshot instead of dumping uuids', () => {
    expect(pageSource).toContain('assetOptions.map(({ instUuid, label })');
    expect(pageSource).not.toContain('label: uuid');
  });

  it('keeps a real height chain so the tab body scrolls instead of being clipped', () => {
    const styleSource = readSource('../page.module.scss');
    expect(styleSource).toMatch(/\.tabContent\s*\{/);
    expect(styleSource).toContain(':global(.ant-tabs-tabpane)');
    expect(styleSource).not.toMatch(/^\s*\.ant-tabs/m);
  });
});
