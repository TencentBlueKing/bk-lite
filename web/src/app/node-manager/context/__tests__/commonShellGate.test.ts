import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = dirname(fileURLToPath(import.meta.url));

describe('node-manager route shells avoid full-page loading gates', () => {
  it('renders children without waiting on useApiClient', () => {
    const source = readFileSync(resolve(root, '../../(pages)/layout.tsx'), 'utf8');
    expect(source).not.toMatch(/isLoading \? null/);
    expect(source).not.toMatch(/useApiClient/);
    expect(source).toMatch(/<CommonProvider>\{children\}<\/CommonProvider>/);
  });

  it('does not replace the whole app with Spin while node enums load', () => {
    const source = readFileSync(resolve(root, '../common.tsx'), 'utf8');
    expect(source).not.toMatch(/from '@\/components\/spin'/);
    expect(source).not.toMatch(/pageLoading \? \(\s*<Spin/);
    expect(source).toMatch(/commonLoading/);
    expect(source).toMatch(/\{children\}/);
  });
});
