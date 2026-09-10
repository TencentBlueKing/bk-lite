import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = dirname(fileURLToPath(import.meta.url));

describe('log and cmdb route shells avoid full-page loading gates', () => {
  it('renders log children without waiting on useApiClient', () => {
    const source = readFileSync(resolve(root, '../../(pages)/layout.tsx'), 'utf8');
    expect(source).not.toMatch(/isLoading \? null/);
    expect(source).toMatch(/<CommonProvider>\{children\}<\/CommonProvider>/);
  });

  it('keeps log CommonProvider children visible while users load', () => {
    const source = readFileSync(resolve(root, '../common.tsx'), 'utf8');
    expect(source).not.toMatch(/pageLoading \? \(\s*<Spin/);
    expect(source).toMatch(/commonLoading/);
    expect(source).toMatch(/\{children\}/);
  });
});
