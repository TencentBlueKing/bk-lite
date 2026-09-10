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
    expect(pathnamePrefixFromPilotFile('ops-analysis/(pages)/view/dashboard.pilot.ts')).toBe(
      '/ops-analysis/view/',
    );
    expect(pathnamePrefixFromPilotFile('monitor/(pages)/event/alert/alert.pilot.ts')).toBe(
      '/monitor/event/alert/',
    );
  });

  it('emits an empty shared manifest without @/app reverse imports', () => {
    const root = 'D:/app/github/bk-lite/web';
    const source = buildPilotsManifestSource(
      [
        `${root}/src/app/monitor/(pages)/view/dashboard/dashboard.pilot.ts`,
        `${root}/src/app/alarm/(pages)/list/list.pilot.ts`,
      ],
      root,
    );
    expect(source).toContain('GENERATED_PAGE_CONTEXT_PILOTS: AiPageContextPilot[] = []');
    expect(source).not.toContain("import('@/app/");
  });
});
