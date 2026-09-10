import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { fingerprintAlertListRows } from '../src/app/monitor/(pages)/event/alert/alertListStamp';

const header = '级别 | 告警名称 | 资产';
const row1 = '严重 | CPU 高 | host-a';
const row2 = '警告 | 磁盘高 | host-b';
const row3 = '提示 | 内存高 | host-c';
const row4 = '严重 | 网络中断 | host-d';
const row4Changed = '警告 | 网络延迟 | host-d';

const headerPlus3 = [header, row1, row2, row3];
const headerPlus4 = [header, row1, row2, row3, row4];
const fourthRowChanged = [header, row1, row2, row3, row4Changed];
const firstThreeChanged = [header, '严重 | CPU 更高 | host-a', row2, row3, row4];

assert.notEqual(
  fingerprintAlertListRows(headerPlus3),
  fingerprintAlertListRows(headerPlus4),
  '表头+3 行与表头+4 行指纹必须不同',
);

assert.notEqual(
  fingerprintAlertListRows(headerPlus4),
  fingerprintAlertListRows(fourthRowChanged),
  '只改第四行指纹必须变化',
);

assert.notEqual(
  fingerprintAlertListRows(headerPlus4),
  fingerprintAlertListRows(firstThreeChanged),
  '只改前三行指纹必须变化',
);

assert.equal(
  fingerprintAlertListRows(headerPlus4),
  fingerprintAlertListRows([...headerPlus4]),
  '完全相同快照指纹必须相同',
);

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const pilotSource = readFileSync(
  join(root, 'src/app/monitor/(pages)/event/alert/alert.pilot.ts'),
  'utf8',
);
const stampSource = readFileSync(
  join(root, 'src/app/monitor/(pages)/event/alert/alertListStamp.ts'),
  'utf8',
);

assert.match(
  pilotSource,
  /from ['"]\.\/alertListStamp['"]/,
  'readAlertListStamp 必须使用抽出的 fingerprintAlertListRows',
);
assert.match(
  pilotSource,
  /rowFingerprint:\s*fingerprintAlertListRows\(rows\)/,
  'readAlertListStamp 必须用抽出函数生成 rowFingerprint',
);
assert.doesNotMatch(
  pilotSource,
  /slice\(\s*0\s*,\s*4\s*\)/,
  'alert.pilot.ts 不得再用 slice(0, 4) 截断行指纹',
);
assert.doesNotMatch(
  stampSource,
  /slice\(\s*0\s*,\s*4\s*\)/,
  '抽出模块不得再用 slice(0, 4) 截断行指纹',
);

console.log('monitor-alert-list-cache-stamp: pass');
