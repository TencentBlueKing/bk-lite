/**
 * MLOps 标注页面不得在翻译调用后回退到中文文本。
 *
 * 运行：pnpm exec tsx scripts/mlops-i18n-fallback-test.ts
 */

import fs from 'node:fs';
import path from 'node:path';

const sourcePath = path.resolve(process.cwd(), 'src/app/mlops/components/annotation/objectDetection.tsx');
const source = fs.readFileSync(sourcePath, 'utf8');
const keys = [
  'datasets.labelExists',
  'datasets.labelInUse',
  'datasets.labelManagement',
  'common.search',
  'datasets.addLabel',
  'datasets.pressEnterToAdd',
];

let failed = 0;

for (const key of keys) {
  const escapedKey = key.replace('.', '\\.');
  const hasChineseFallback = new RegExp(`t\\('${escapedKey}'\\)\\s*\\|\\|\\s*['"][^'"]*[\\p{Script=Han}]`, 'u').test(source);
  if (hasChineseFallback) {
    failed += 1;
    console.error(`✗ ${key} 不应保留中文 fallback`);
  } else {
    console.log(`✓ ${key} 未保留中文 fallback`);
  }
}

if (failed > 0) {
  process.exit(1);
}
