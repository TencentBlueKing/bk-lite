import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));

describe('signin screen query passthrough', () => {
  it('merges screen from the login page onto post-login targets', () => {
    const signinClient = readFileSync(resolve(here, '../SigninClient.tsx'), 'utf8');
    expect(signinClient).toMatch(/withScreenQuery\(/);
    expect(signinClient).toMatch(/isScreenModeEnabled\(window\.location\.search\)/);
    expect(signinClient).toMatch(/window\.location\.href = nextUrl/);

    const signinPage = readFileSync(resolve(here, '../page.tsx'), 'utf8');
    expect(signinPage).toMatch(/withScreenQuery\(/);
    expect(signinPage).toMatch(/resolvedSearchParams\.screen/);
  });
});
