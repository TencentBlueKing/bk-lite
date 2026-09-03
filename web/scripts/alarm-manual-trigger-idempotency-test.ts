import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const alarmDir = resolve(here, '../src/app/alarm');

const settingsSource = readFileSync(resolve(alarmDir, 'api/settings.ts'), 'utf8');
const actionSource = readFileSync(
  resolve(alarmDir, '(pages)/alarms/components/alarmAction.tsx'),
  'utf8'
);
const timelineSource = readFileSync(
  resolve(alarmDir, '(pages)/alarms/components/actionTimeline.tsx'),
  'utf8'
);

assert.match(
  settingsSource,
  /action_execution\/manual_trigger/,
  'manualTriggerAction must call the manual_trigger endpoint'
);
assert.match(
  settingsSource,
  /'Idempotency-Key':\s*crypto\.randomUUID\(\)/,
  'manual_trigger must send a per-click Idempotency-Key header within 128 chars'
);

assert.match(
  actionSource,
  /await manualTriggerAction\(\{ alert_id: alertId, rule_id: rule\.id \}\)/,
  'alarm action dropdown must keep using the shared manualTriggerAction client'
);
assert.match(
  timelineSource,
  /await manualTriggerAction\(\{ alert_id: alertId, rule_id: item\.rule \}\)/,
  'action timeline rerun must keep using the shared manualTriggerAction client'
);

assert.doesNotMatch(
  `${actionSource}\n${timelineSource}`,
  /action_execution\/manual_trigger/,
  'UI callers must not bypass the shared client that attaches Idempotency-Key'
);

console.log('alarm manual trigger idempotency test passed');
