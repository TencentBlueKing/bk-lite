import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const source = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), './index.tsx'),
  'utf8',
);

describe('Introduction width contract', () => {
  it('fills the pane instead of defaulting to an 800px floor that becomes a left column', () => {
    expect(source).toMatch(/w-full min-w-0 shrink-0/);
    expect(source).toMatch(/minWidth != null \? \{ minWidth \} : \{\}/);
    expect(source).not.toMatch(/minWidth \?\? 800/);
  });
});
