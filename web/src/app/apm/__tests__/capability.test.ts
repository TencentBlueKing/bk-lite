import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { APP_CAPABILITY_LOADERS } from '@/context/appCapabilities/catalog';

const capabilitySource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../capability.ts'),
  'utf8',
);

describe('apm capability', () => {
  it('registers service overview and call chain as independent dynamic imports', () => {
    expect(APP_CAPABILITY_LOADERS.apm).toBeTypeOf('function');
    expect(capabilitySource).toContain("'apm.serviceOverview'");
    expect(capabilitySource).toContain("'apm.callChain'");
    expect(capabilitySource).toContain(
      "import('@/app/apm/components/public/ServiceOverviewWidget')",
    );
    expect(capabilitySource).toContain(
      "import('@/app/apm/components/public/CallChainWidget')",
    );
    expect(capabilitySource).not.toMatch(
      /import ServiceOverviewWidget from ['"]@\/app\/apm\/components\/public\/ServiceOverviewWidget['"]/,
    );
    expect(capabilitySource).not.toMatch(
      /import CallChainWidget from ['"]@\/app\/apm\/components\/public\/CallChainWidget['"]/,
    );
  });
});
