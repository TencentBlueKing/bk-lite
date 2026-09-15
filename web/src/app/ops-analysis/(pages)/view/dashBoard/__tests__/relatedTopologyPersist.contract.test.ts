import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const dashboardSource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../index.tsx'),
  'utf8',
);

describe('dashboard relatedTopology persist mapping', () => {
  it('writes relatedTopology on add and edit so confirm can land instUuid', () => {
    expect(dashboardSource).toContain('relatedTopology: config.relatedTopology');
    expect(dashboardSource).toContain('relatedTopology: values.relatedTopology');
  });
});
