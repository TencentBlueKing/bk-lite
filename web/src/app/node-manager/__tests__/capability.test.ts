import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { APP_CAPABILITY_LOADERS } from '@/context/appCapabilities/catalog';

const capabilitySource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../capability.ts'),
  'utf8',
);

describe('node-manager capability', () => {
  it('registers the node status widget on the sold app name node', () => {
    expect(APP_CAPABILITY_LOADERS.node).toBeTypeOf('function');
    expect(capabilitySource).toContain("'node.nodeStatus'");
    expect(capabilitySource).toContain(
      "import('@/app/node-manager/components/public/NodeStatusWidget')",
    );
    expect(capabilitySource).not.toMatch(
      /import NodeStatusWidget from ['"]@\/app\/node-manager\/components\/public\/NodeStatusWidget['"]/,
    );
  });
});
