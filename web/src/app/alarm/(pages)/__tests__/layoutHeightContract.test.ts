import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const source = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../layout.tsx'),
  'utf8',
);

describe('alarm pages layout height contract', () => {
  it('passes remaining pane height through AliveScope to the page', () => {
    expect(source).toMatch(
      /flex h-full min-h-0 w-full flex-1 flex-col/,
    );
  });
});
