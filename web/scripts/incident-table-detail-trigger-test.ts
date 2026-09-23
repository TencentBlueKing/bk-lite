import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  INCIDENT_DETAIL_TRIGGER_COLUMN_KEYS,
  getIncidentDetailTriggerCellProps,
  isIncidentDetailTriggerColumn,
} from '../src/app/alarm/utils/incidentTableColumns';

const here = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(
  resolve(here, '../src/app/alarm/(pages)/incidents/page.tsx'),
  'utf8'
);

assert.deepEqual(
  [...INCIDENT_DETAIL_TRIGGER_COLUMN_KEYS],
  ['level', 'title', 'alert_count', 'status', 'duration']
);
assert.equal(isIncidentDetailTriggerColumn('title'), true);
assert.equal(isIncidentDetailTriggerColumn('alert_count'), true);
assert.equal(isIncidentDetailTriggerColumn('created_at'), false);

const opened: unknown[] = [];
const record = { id: 9, incident_id: 'inc-9' };
const titleCell = getIncidentDetailTriggerCellProps(record, 'title', (row) =>
  opened.push(row)
);
assert.equal(titleCell.className, 'cursor-pointer');
titleCell.onClick?.({ stopPropagation() {} });
assert.deepEqual(opened, [record]);
assert.deepEqual(
  getIncidentDetailTriggerCellProps(record, 'created_at', () => {
    throw new Error('non-trigger column must not open detail');
  }),
  {}
);

assert.match(pageSource, /getIncidentDetailTriggerCellProps/);
assert.match(
  pageSource,
  /onCell:\s*\(record\)\s*=>\s*getIncidentDetailTriggerCellProps/
);
for (const key of INCIDENT_DETAIL_TRIGGER_COLUMN_KEYS) {
  assert.match(
    pageSource,
    new RegExp(`getIncidentDetailTriggerCellProps\\(record, '${key}'`)
  );
}

console.log('incident table detail trigger test passed');
