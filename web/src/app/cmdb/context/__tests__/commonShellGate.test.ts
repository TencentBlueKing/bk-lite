import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = dirname(fileURLToPath(import.meta.url));

describe('cmdb CommonProvider route shell', () => {
  it('does not replace the whole app with Spin while models and users load', () => {
    const source = readFileSync(resolve(root, '../common.tsx'), 'utf8');
    expect(source).not.toMatch(/from '@\/components\/spin'/);
    expect(source).not.toMatch(/pageLoading \? \(\s*<Spin/);
    expect(source).toMatch(/commonLoading/);
    expect(source).toMatch(/\{children\}/);
  });
});
