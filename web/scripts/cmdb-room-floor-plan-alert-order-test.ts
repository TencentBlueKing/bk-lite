import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
  resolve(
    here,
    '../src/app/cmdb/(pages)/assetData/detail/relationships/roomFloorPlan.tsx'
  ),
  'utf8'
);
const zhLocale = readFileSync(resolve(here, '../src/app/cmdb/locales/zh.json'), 'utf8');
const enLocale = readFileSync(resolve(here, '../src/app/cmdb/locales/en.json'), 'utf8');

const conflictAlert = source.indexOf("message={t('Model.rackCellConflict')}");
const missingLocationAlert = source.indexOf("message={`${t('Model.rackLocationMissing')}");
const invalidLocationAlert = source.indexOf("message={`${t('Model.rackLocationInvalid')}");
const legend = source.indexOf('<div className="rf-legend">');
const stage = source.indexOf('<div className="rf-stage">');

assert.match(
  source,
  /data\.unplaced\.filter\(\s*\(rack\) => rack\.unplaced_reason === 'missing_location'\s*\)/,
  '机房视图必须单独筛选位置为空的机柜'
);
assert.match(
  source,
  /data\.unplaced\.filter\(\s*\(rack\) => rack\.unplaced_reason === 'invalid_location'\s*\)/,
  '机房视图必须单独筛选位置格式错误的机柜'
);
assert.match(zhLocale, /"rackLocationMissing": "未定位机柜（位置为空）"/);
assert.match(zhLocale, /"rackLocationInvalid": "未定位机柜（位置格式不正确，应为 A01 格式）"/);
assert.match(enLocale, /"rackLocationMissing": "Racks without a position"/);
assert.match(enLocale, /"rackLocationInvalid": "Racks with an invalid position \(expected format: A01\)"/);
assert.ok(
  conflictAlert >= 0 &&
    missingLocationAlert >= 0 &&
    invalidLocationAlert >= 0 &&
    legend >= 0 &&
    stage >= 0
);
assert.ok(
  conflictAlert < missingLocationAlert &&
    missingLocationAlert < invalidLocationAlert &&
    invalidLocationAlert < legend &&
    legend < stage,
  '机房数据异常提示必须按错误、警告顺序显示在图例和画布之前'
);

console.log('PASS cmdb-room-floor-plan-alert-order');
