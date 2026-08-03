import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import menu from '../src/app/apm/constants/menu.json';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');

for (const locale of ['zh', 'en'] as const) {
  for (const item of menu[locale]) {
    assert.equal(
      existsSync(join(webRoot, 'src/app', item.url, 'page.tsx')),
      true,
      `${locale} APM 菜单 ${item.title} 指向不存在的页面 ${item.url}`,
    );
  }
}

console.log('APM menu route checks passed');
