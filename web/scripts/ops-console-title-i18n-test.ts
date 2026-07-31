/**
 * Ops Console 欢迎标题 i18n 契约。
 *
 * 运行：pnpm exec tsx scripts/ops-console-title-i18n-test.ts
 */

import fs from 'node:fs';
import path from 'node:path';

const read = (relativePath: string) => fs.readFileSync(path.resolve(process.cwd(), relativePath), 'utf8');
const pageSource = read('src/app/ops-console/(pages)/home/page.tsx');
const zhMessages = JSON.parse(read('src/app/ops-console/locales/zh.json'));
const enMessages = JSON.parse(read('src/app/ops-console/locales/en.json'));

let failed = 0;

const assert = (condition: boolean, message: string) => {
  if (condition) {
    console.log(`✓ ${message}`);
  } else {
    failed += 1;
    console.error(`✗ ${message}`);
  }
};

assert(
  pageSource.includes("t('opsConsole.console', undefined, { portalName })"),
  '欢迎标题应通过 t() 传入 portalName 插值',
);
assert(!pageSource.includes("locale === 'zh-CN'"), '欢迎标题不应自行判断中文 locale');
assert(zhMessages.opsConsole.console.includes('{portalName}'), '中文欢迎标题应包含 portalName 占位符');
assert(enMessages.opsConsole.console.includes('{portalName}'), '英文欢迎标题应包含 portalName 占位符');

if (failed > 0) {
  process.exit(1);
}
