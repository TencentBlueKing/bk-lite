import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const paramsConfigSource = readFileSync(
  fileURLToPath(
    new URL(
      '../src/app/ops-analysis/components/paramsConfig.tsx',
      import.meta.url,
    ),
  ),
  'utf8',
);

assert.match(
  paramsConfigSource,
  /param\.filterType !== 'fixed'/,
  '固定参数不应显示组件级输入配置入口',
);

console.log('ops analysis fixed parameter config tests passed');
