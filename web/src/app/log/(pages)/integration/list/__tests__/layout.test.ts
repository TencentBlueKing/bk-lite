import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const pageSource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../page.tsx'),
  'utf8',
);

describe('log integration card grid layout', () => {
  it('uses content-sized rows inside the fixed-height scrolling grid', () => {
    expect(pageSource).toContain('auto-rows-max');
    expect(pageSource).toContain('overflow-y-auto');
  });
});
