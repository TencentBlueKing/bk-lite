import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string) {
  return readFileSync(resolve(here, relativePath), 'utf8');
}

describe('alarm related topology app-capability isolation', () => {
  it('does not statically import ops-analysis modules', () => {
    const hosts = [
      readSource('../index.tsx'),
      readSource('../../../(pages)/alarms/components/alarmDetail.tsx'),
      readSource('../../alarm-detail-drawer/index.tsx'),
    ];

    for (const source of hosts) {
      expect(source).not.toMatch(/from ['"]@\/app\/ops-analysis/);
      expect(source).not.toContain('operation_analysis');
    }
  });

  it('loads the widget through the shared capability seam', () => {
    const tabSource = readSource('../index.tsx');
    expect(tabSource).toContain("useAppCapability('ops-analysis')");
    expect(tabSource).toContain('RelatedTopologyWidget');
    expect(tabSource).toContain('loadWidget()');
    expect(tabSource).toContain('.catch(');
    expect(tabSource).not.toContain('relatedTopologyAccess');
  });

  it('passes a single instUuid into the widget and only shows a selector for multiple centers', () => {
    const tabSource = readSource('../index.tsx');
    expect(tabSource).toContain('<Widget key={`${instUuid}:${refreshNonce}`} instUuid={instUuid} />');
    expect(tabSource).not.toMatch(/instUuid=\{\[/);
    expect(tabSource).toContain('centers.length > 1');
  });

  it('shows a failed state instead of spinning when the chunk cannot load', () => {
    const tabSource = readSource('../index.tsx');
    expect(tabSource).toContain('ReloadOutlined');
    expect(tabSource).toContain('common.refresh');
    expect(tabSource).toContain('common.loadFailed');
  });
});
