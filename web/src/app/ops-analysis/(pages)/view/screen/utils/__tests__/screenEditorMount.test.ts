import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('screen editor mount', () => {
  it('keeps the canvas in one parent when edit mode closes', () => {
    const source = readFileSync(
      resolve(process.cwd(), 'src/app/ops-analysis/(pages)/view/screen/index.tsx'),
      'utf8',
    );
    const canvasSlots = source.match(/\{screenCanvas\}/g) ?? [];
    expect(canvasSlots).toHaveLength(1);
    expect(source).not.toMatch(/\)\s*:\s*\(\s*screenCanvas\s*\)/);
  });
});
