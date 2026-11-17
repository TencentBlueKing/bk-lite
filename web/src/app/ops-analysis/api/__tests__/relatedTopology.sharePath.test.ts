import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { RELATED_TOPOLOGY_API_PATH, relatedTopologyApiPath } from '@/app/ops-analysis/api/relatedTopology';

const widgetSource = readFileSync(
  resolve(
    dirname(fileURLToPath(import.meta.url)),
    '../../components/widgets/relatedTopology/index.tsx',
  ),
  'utf8',
);

describe('related topology share transport', () => {
  it('keeps the workbench query on the scene widget API', () => {
    expect(RELATED_TOPOLOGY_API_PATH).toBe(
      '/operation_analysis/api/scene_widgets/related_topology/',
    );
  });

  it('routes share sessions through dashboard_share with the session id', () => {
    expect(relatedTopologyApiPath('share-session-abc', '/ops-analysis/share/session/share-session-abc')).toBe(
      '/operation_analysis/api/dashboard_share/session/share-session-abc/related_topology/',
    );
    expect(relatedTopologyApiPath(undefined, '/ops-analysis/display/view')).toBe(
      '/operation_analysis/api/screen_display/current/related_topology/',
    );
    expect(widgetSource).toContain('useShareMode');
    expect(widgetSource).toContain('params.sessionId');
  });
});
