import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../');
const subLayoutSource = readFileSync(resolve(root, 'index.tsx'), 'utf8');
const layoutSubLayoutSource = readFileSync(
  resolve(root, '../layout/sub-layout/index.tsx'),
  'utf8',
);

describe('WithSideMenuLayout overflow contract', () => {
  it.each([
    ['components/sub-layout', subLayoutSource],
    ['components/layout/sub-layout', layoutSubLayoutSource],
  ])('%s keeps main pane shrinkable so wide tables can scroll', (_label, source) => {
    expect(source).toMatch(/min-h-0 min-w-0 flex-1 flex-col overflow-hidden/);
    expect(source).toMatch(
      /flex-1 min-h-0 min-w-0 overflow-auto rounded-md p-4/,
    );
    expect(source).toMatch(
      /flex h-full min-h-0 min-w-0 w-full grow flex-1 overflow-hidden/,
    );
  });
});
