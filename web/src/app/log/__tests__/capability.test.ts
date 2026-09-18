import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { APP_CAPABILITY_LOADERS } from '@/context/appCapabilities/catalog';

const capabilitySource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../capability.ts'),
  'utf8',
);

describe('log capability', () => {
  it('registers the alert raw log widget as a per-key dynamic import', () => {
    expect(APP_CAPABILITY_LOADERS.log).toBeTypeOf('function');
    expect(capabilitySource).toContain("'log.alertRawLog'");
    expect(capabilitySource).toContain(
      "import('@/app/log/components/public/AlertRawLogWidget')",
    );
    expect(capabilitySource).not.toMatch(
      /import AlertRawLogWidget from ['"]@\/app\/log\/components\/public\/AlertRawLogWidget['"]/,
    );
  });
});
