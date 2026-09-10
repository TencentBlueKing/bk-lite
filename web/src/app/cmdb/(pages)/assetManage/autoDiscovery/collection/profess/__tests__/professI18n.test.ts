import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(resolve(root, '../page.tsx'), 'utf8');

describe('professional collection content i18n', () => {
  it('translates the All category tab', () => {
    expect(source).toMatch(/name:\s*t\(['"]all['"]\)/);
    expect(source).not.toMatch(/name:\s*['"]全部['"]/);
  });

  it('refetches the collect model tree when locale changes', () => {
    expect(source).toMatch(/useLocale\(\)/);
    expect(source).toMatch(/fetchCategoryData\(\);[\s\S]*\}, \[locale\]\)/);
  });
});
