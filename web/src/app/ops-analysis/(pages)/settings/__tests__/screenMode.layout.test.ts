import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const source = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../layout.tsx'),
  'utf8',
);

describe('ops-analysis settings screen mode', () => {
  it('always wraps settings in WithSideMenuLayout so screen hide lives in the layout component', () => {
    expect(source).toMatch(/OpsAnalysisProvider/);
    expect(source).toMatch(/<WithSideMenuLayout/);
    expect(source).toMatch(/layoutType="segmented"/);
    expect(source).toMatch(/pagePathName="\/ops-analysis\/settings\/"/);
    expect(source).not.toMatch(/isScreenModeEnabled/);
    expect(source).not.toMatch(/screenMode \? \(\s*children\s*\) : \(/);
  });
});
