import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const dir = dirname(fileURLToPath(import.meta.url));

function read(relativePath: string) {
  return readFileSync(join(dir, relativePath), 'utf8');
}

describe('application association context hint', () => {
  const page = read('../page.tsx');
  const modelApi = read('../../../../../../api/model.ts');
  const zh = read('../../../../../../locales/zh.json');
  const en = read('../../../../../../locales/en.json');

  it('shows the membership hint only after the application model guard', () => {
    const hintAt = page.indexOf('ciContextHint');
    const guardAt = page.search(/modelId === ['"]application['"]/);
    expect(guardAt).toBeGreaterThanOrEqual(0);
    expect(hintAt).toBeGreaterThan(guardAt);
    expect(page).toContain("t('Model.ciContextHint')");
  });

  it('does not add a membership column', () => {
    expect(page).not.toMatch(/dataIndex:\s*['"][^'"]*(membership|context_link|计入)[^'"]*['"]/);
    expect(page).not.toContain('计入应用成员');
    expect(page).toContain("dataIndex: 'required'");
    expect(page).toContain("dataIndex: 'island_count'");
  });

  it('puts the override in More and calls the context link API', () => {
    expect(page).toContain('ciContextMore');
    expect(page).toContain('setAssociationContextLink');
    expect(page).toContain("modelId === 'application'");
    expect(modelApi).toContain('/cmdb/api/model/association/${modelAsstId}/context_link/');
    expect(modelApi).toContain('context_link: contextLink');
  });

  it('keeps the hint copy in both locales', () => {
    expect(zh).toContain('应用的运行于 / 关联会记成第 1 层成员；这些成员上的运行于记成第 2 层。不必给 MySQL、Redis 等分别打标。');
    expect(en).toContain('Run/connect from an application become layer-1 members; run from those members becomes layer 2. You do not tag MySQL, Redis, etc. separately.');
    expect(zh).toContain('"ciContextMore": "更多"');
    expect(en).toContain('"ciContextFollow"');
    expect(en).toContain('"ciContextInclude"');
    expect(en).toContain('"ciContextExclude"');
    JSON.parse(zh);
    JSON.parse(en);
  });
});
