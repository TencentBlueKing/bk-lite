import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const source = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../layout.tsx'),
  'utf8',
);

describe('ops-analysis settings screen mode', () => {
  it('skips the segmented settings menu in screen mode and keeps it otherwise', () => {
    expect(source).toMatch(/isScreenModeEnabled\(searchParams\)/);
    expect(source).toMatch(/OpsAnalysisProvider/);
    expect(source).toMatch(/screenMode \? \(\s*children\s*\) : \(/);
    expect(source).toMatch(/<WithSideMenuLayout/);
    expect(source).toMatch(/layoutType="segmented"/);
    expect(source).toMatch(/pagePathName="\/ops-analysis\/settings\/"/);
  });
});
