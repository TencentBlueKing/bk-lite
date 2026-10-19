import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));

describe('资产总览工作面层级', () => {
  const pageSource = readFileSync(resolve(here, '../page.tsx'), 'utf8');

  it('让实体卡片直接落在默认画布上，不再增加整页白色容器', () => {
    expect(pageSource).toContain(
      'className="flex h-full min-h-0 flex-col overflow-hidden"'
    );
    expect(pageSource).not.toContain(
      'rounded-lg bg-[var(--color-bg)] p-3'
    );
  });

  it('保留列表型页面靠右搜索和原有分类卡片结构', () => {
    expect(pageSource).toContain('className="mb-3 flex justify-end"');
    expect(pageSource).toContain('<Input.Search');
    expect(pageSource).toContain('className={assetsOverviewStyle.card}');
  });
});
