import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const scssPath = join(dirname(fileURLToPath(import.meta.url)), '../index.module.scss');

describe('SystemManagerFillTable overflow', () => {
  it('does not force-hide horizontal table scroll', () => {
    const scss = readFileSync(scssPath, 'utf8');
    expect(scss).not.toMatch(/overflow-x\s*:\s*hidden/);
  });
});
