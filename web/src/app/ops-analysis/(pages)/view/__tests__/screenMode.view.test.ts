import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const source = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../page.tsx'),
  'utf8',
);

describe('ops-analysis view screen mode', () => {
  it('hides the directory sidebar and collapse control in screen mode', () => {
    expect(source).toMatch(/hidden=\{screenMode\}/);
    expect(source).toMatch(/!screenMode && \(/);
    expect(source).toMatch(/LeftOutlined|RightOutlined/);
  });

  it('routes canvas switches through a screen-preserving href builder', () => {
    expect(source).toMatch(/buildOpsAnalysisViewHref\(/);
    expect(source).not.toMatch(/router\.push\(`\/ops-analysis\/view\?\$\{params\}`\)/);
  });
});
