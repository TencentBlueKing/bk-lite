import { describe, expect, it } from 'vitest';

import { buildPilotsManifestSource, pathnamePrefixFromPilotFile } from '../../../../scripts/generate-ai-pilots-lib.mjs';

describe('generate-ai-pilots', () => {
  it('derives pathname prefixes from pilot file locations', () => {
    expect(pathnamePrefixFromPilotFile('monitor/(pages)/view/dashboard/dashboard.pilot.ts')).toBe(
      '/monitor/view/dashboard/',
    );
    expect(pathnamePrefixFromPilotFile('alarm/(pages)/incident/list.pilot.ts')).toBe('/alarm/incident/');
    expect(pathnamePrefixFromPilotFile('monitor/(pages)/view/dashboard/[objectKey]/detail.pilot.ts')).toBe(
      '/monitor/view/dashboard/',
    );
  });

  it('builds a deterministic manifest', () => {
    const root = 'D:/app/github/bk-lite/web';
    const source = buildPilotsManifestSource(
      [
        `${root}/src/app/monitor/(pages)/view/dashboard/dashboard.pilot.ts`,
        `${root}/src/app/alarm/(pages)/list/list.pilot.ts`,
      ],
      root,
    );
    expect(source).toContain("pathname.includes('/alarm/list/')");
    expect(source).toContain("pathname.includes('/monitor/view/dashboard/')");
    expect(source.indexOf('/alarm/list/')).toBeLessThan(source.indexOf('/monitor/view/dashboard/'));
    expect(source).toContain("import('@/app/monitor/(pages)/view/dashboard/dashboard.pilot')");
  });
});
