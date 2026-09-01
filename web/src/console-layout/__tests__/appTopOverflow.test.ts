import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const source = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../../app/layout.tsx'),
  'utf8',
);

describe('app-top chrome overflow', () => {
  it('does not clip the shell on the x-axis after adding the left rail', () => {
    expect(source).not.toMatch(/showAppTopSide \? 'h-screen overflow-hidden'/);
    expect(source).toMatch(/overflow-x-auto overflow-y-hidden/);
    expect(source).toMatch(/min-w-0 flex-col py-4 pr-4/);
  });
});
