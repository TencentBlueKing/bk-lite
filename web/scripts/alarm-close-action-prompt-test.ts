import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const alarmDir = resolve(here, '../src/app/alarm');

const actionSource = readFileSync(
  resolve(alarmDir, '(pages)/alarms/components/alarmAction.tsx'),
  'utf8'
);
const timelineSource = readFileSync(
  resolve(alarmDir, '(pages)/alarms/components/actionTimeline.tsx'),
  'utf8'
);
const detailSource = readFileSync(
  resolve(alarmDir, '(pages)/alarms/components/alarmDetail.tsx'),
  'utf8'
);

assert.match(
  actionSource,
  /canManuallyTriggerAlertAction/,
  'manual trigger dropdown must be gated by active alert status'
);
assert.match(
  actionSource,
  /shouldPromptActionOnClose/,
  'manual close must prompt eligible non-auto close-trigger rules'
);
assert.match(
  actionSource,
  /runManualActionTrigger/,
  'close prompt must reuse the existing manual execute flow'
);

assert.match(
  timelineSource,
  /allowRerun/,
  'action timeline rerun must be disableable for ended alerts'
);
assert.match(
  detailSource,
  /allowRerun=\{/,
  'alarm detail must pass ended-status rerun gating into ActionTimeline'
);

console.log('alarm close action prompt test passed');
