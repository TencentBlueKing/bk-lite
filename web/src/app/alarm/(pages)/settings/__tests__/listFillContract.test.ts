import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const listPages = [
  'correlationRules/page.tsx',
  'shieldStrategy/page.tsx',
  'alertAssign/page.tsx',
  'alertEnrichment/page.tsx',
  'actionRules/page.tsx',
  'actionRecords/page.tsx',
  'notificationTemplates/page.tsx',
  'operationLog/page.tsx',
];

describe('alarm settings list pages fill remaining pane height', () => {
  it.each(listPages)('%s stretches the table card instead of hugging rows', (relativePath) => {
    const source = readFileSync(resolve(root, relativePath), 'utf8');
    expect(source).toMatch(/flex min-h-0 flex-1 flex-col/);
    expect(source).toMatch(/min-h-0 flex-1/);
    expect(source).not.toMatch(/scroll=\{\{\s*y:\s*['"]auto['"]/);
    expect(source).not.toMatch(/calc\(100vh/);
  });
});
