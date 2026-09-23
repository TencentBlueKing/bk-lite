import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { buildPilotsManifestSource, pathnamePrefixFromPilotFile } from '../../../../scripts/generate-ai-pilots-lib.mjs';

const root = dirname(fileURLToPath(import.meta.url));

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
    expect(pathnamePrefixFromPilotFile('monitor/(pages)/view/view.pilot.ts')).toBe(
      '/monitor/view/',
    );
    expect(pathnamePrefixFromPilotFile('monitor/(pages)/search/search.pilot.ts')).toBe(
      '/monitor/search/',
    );
    expect(pathnamePrefixFromPilotFile('monitor/(pages)/event/strategy/strategy.pilot.ts')).toBe(
      '/monitor/event/strategy/',
    );
    expect(pathnamePrefixFromPilotFile('monitor/(pages)/event/strategy/detail/strategyDetail.pilot.ts')).toBe(
      '/monitor/event/strategy/detail/',
    );
    expect(pathnamePrefixFromPilotFile('monitor/(pages)/integration/list/list.pilot.ts')).toBe(
      '/monitor/integration/list/',
    );
    expect(pathnamePrefixFromPilotFile('monitor/(pages)/integration/asset/asset.pilot.ts')).toBe(
      '/monitor/integration/asset/',
    );
    expect(pathnamePrefixFromPilotFile('alarm/(pages)/alarms/alarms.pilot.ts')).toBe(
      '/alarm/alarms/',
    );
    expect(pathnamePrefixFromPilotFile('alarm/(pages)/incidents/incidents.pilot.ts')).toBe(
      '/alarm/incidents/',
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

  it('registers alarm pilots from app pages instead of the shared generated list', () => {
    const alarmsPage = readFileSync(
      resolve(root, '../../../app/alarm/(pages)/alarms/page.tsx'),
      'utf8',
    );
    const incidentsPage = readFileSync(
      resolve(root, '../../../app/alarm/(pages)/incidents/page.tsx'),
      'utf8',
    );
    expect(alarmsPage).toContain("import './register-alarms-pilot'");
    expect(incidentsPage).toContain("import './register-incidents-pilot'");
  });

  it('registers log search and apm pilots from app pages instead of the shared generated list', () => {
    const searchPage = readFileSync(
      resolve(root, '../../../app/log/(pages)/search/page.tsx'),
      'utf8',
    );
    const servicePage = readFileSync(
      resolve(root, '../../../app/apm/services/[serviceId]/page.tsx'),
      'utf8',
    );
    const tracePage = readFileSync(
      resolve(root, '../../../app/apm/explore/traces/[traceId]/page.tsx'),
      'utf8',
    );
    expect(searchPage).toContain("import './register-search-pilot'");
    expect(servicePage).toContain("import './register-service-pilot'");
    expect(tracePage).toContain("import './register-trace-pilot'");
  });
});
