import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = dirname(fileURLToPath(import.meta.url));

describe('ssl cer collection task', () => {
  it('routes ssl_cer to a dedicated form and disables IP range', () => {
    const page = readFileSync(resolve(root, '../../page.tsx'), 'utf8');
    const base = readFileSync(resolve(root, '../baseTask.tsx'), 'utf8');
    expect(page).toMatch(/model_id === 'ssl_cer'/);
    expect(page).toMatch(/SslCerTask/);
    expect(base).toMatch(/modelId === 'ssl_cer'/);
    expect(base).toMatch(/isSslCerTask/);
  });

  it('submits selected instances without credentials or IP range', () => {
    const source = readFileSync(resolve(root, '../sslCerTask.tsx'), 'utf8');
    expect(source).not.toMatch(/CredentialPoolEditor/);
    expect(source).toMatch(/ip_range:\s*''/);
    expect(source).toMatch(/credential:\s*\[\s*\]/);
    expect(source).toMatch(/task_type:\s*'protocol'|driver_type:\s*'protocol'/);
  });
});
