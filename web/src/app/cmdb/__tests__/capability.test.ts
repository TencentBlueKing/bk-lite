import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { APP_CAPABILITY_LOADERS } from '@/context/appCapabilities/catalog';

const capabilitySource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../capability.ts'),
  'utf8',
);

describe('cmdb capability', () => {
  it('registers the base-info widget as a per-key dynamic import', () => {
    expect(APP_CAPABILITY_LOADERS.cmdb).toBeTypeOf('function');
    expect(capabilitySource).toContain("'cmdb.baseInfo'");
    expect(capabilitySource).toContain(
      "import('@/app/cmdb/components/public/BaseInfoWidget')",
    );
    expect(capabilitySource).not.toMatch(
      /import BaseInfoWidget from ['"]@\/app\/cmdb\/components\/public\/BaseInfoWidget['"]/,
    );
  });
});
