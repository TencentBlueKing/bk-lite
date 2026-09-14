import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { APP_CAPABILITY_LOADERS } from '@/context/appCapabilities/catalog';

const capabilitySource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../capability.ts'),
  'utf8',
);

describe('monitor capability', () => {
  it('registers public widgets as per-key dynamic imports', () => {
    expect(APP_CAPABILITY_LOADERS.monitor).toBeTypeOf('function');
    expect(capabilitySource).toContain("'monitor.monitorView'");
    expect(capabilitySource).toContain("'monitor.alertList'");
    expect(capabilitySource).toContain(
      "import('@/app/monitor/components/public/MonitorViewWidget')",
    );
    expect(capabilitySource).toContain(
      "import('@/app/monitor/components/public/AlertListWidget')",
    );
    expect(capabilitySource).not.toMatch(
      /import MonitorViewWidget from ['"]@\/app\/monitor\/components\/public\/MonitorViewWidget['"]/,
    );
  });
});
