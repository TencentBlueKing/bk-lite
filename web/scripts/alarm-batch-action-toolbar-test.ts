import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(
  resolve(here, '../src/app/alarm/(pages)/alarms/page.tsx'),
  'utf8'
);

assert.match(
  pageSource,
  /^import AlarmAction from '\.\/components\/alarmAction';/m,
  'active alarm list must import the batch AlarmAction toolbar'
);
assert.match(
  pageSource,
  /<AlarmAction[\s\S]*?rowData=\{selectedRowData\}[\s\S]*?displayMode="dropdown"[\s\S]*?showAll[\s\S]*?onAction=\{onRefresh\}[\s\S]*?\/>/,
  'active alarm list must render a top-right batch action dropdown for selected alerts'
);
assert.doesNotMatch(
  pageSource,
  /顶部 batch AlarmAction 暂时隐藏/,
  'batch AlarmAction must not stay commented out as a temporary hide'
);

console.log('alarm batch action toolbar test passed');
