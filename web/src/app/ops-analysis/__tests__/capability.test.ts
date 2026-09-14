import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { APP_CAPABILITY_LOADERS } from '@/context/appCapabilities/catalog';
import { RELATED_TOPOLOGY_API_PATH } from '@/app/ops-analysis/api/relatedTopology';

const capabilitySource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../capability.ts'),
  'utf8',
);

describe('ops-analysis capability', () => {
  it('registers public widgets as per-key dynamic imports', () => {
    expect(APP_CAPABILITY_LOADERS['ops-analysis']).toBeTypeOf('function');
    expect(capabilitySource).toContain("'ops-analysis.relatedTopology'");
    expect(capabilitySource).toContain("'ops-analysis.networkStatusTopology'");
    expect(capabilitySource).toContain("'ops-analysis.application3D'");
    expect(capabilitySource).toContain(
      "import('@/app/ops-analysis/components/widgets/relatedTopology')",
    );
    expect(capabilitySource).toContain(
      "import('@/app/ops-analysis/components/widgets/networkStatusTopology/embed')",
    );
    expect(capabilitySource).toContain(
      "import('@/app/ops-analysis/components/widgets/application3D/embed')",
    );
    expect(capabilitySource).not.toMatch(
      /import RelatedTopology from ['"]@\/app\/ops-analysis\/components\/widgets\/relatedTopology['"]/,
    );
    expect(capabilitySource).not.toMatch(
      /import NetworkStatusTopologyEmbed from ['"]@\/app\/ops-analysis\/components\/widgets\/networkStatusTopology\/embed['"]/,
    );
    expect(capabilitySource).not.toMatch(
      /import Application3DEmbed from ['"]@\/app\/ops-analysis\/components\/widgets\/application3D\/embed['"]/,
    );
  });

  it('keeps the related topology query on the ops-analysis widget API', () => {
    expect(RELATED_TOPOLOGY_API_PATH).toBe(
      '/operation_analysis/api/scene_widgets/related_topology/',
    );
  });

  it('does not put a retry button inside the related topology canvas', () => {
    const widgetSource = readFileSync(
      resolve(
        dirname(fileURLToPath(import.meta.url)),
        '../components/widgets/relatedTopology/index.tsx',
      ),
      'utf8',
    );
    expect(widgetSource).not.toContain("t('common.retry')");
  });
});
