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
const modalSource = readFileSync(
  resolve(alarmDir, '(pages)/alarms/components/manualActionExecuteModal.tsx'),
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
  /runManualActionTrigger/,
  'alarm action dropdown must go through runManualActionTrigger'
);
assert.match(
  timelineSource,
  /runManualActionTrigger/,
  'action timeline rerun must go through runManualActionTrigger'
);
assert.match(
  timelineSource,
  /getActionRule/,
  'action timeline rerun must load the latest action_config via getActionRule'
);

assert.doesNotMatch(
  `${actionSource}\n${timelineSource}`,
  /action_execution\/manual_trigger/,
  'UI callers must not bypass the shared client that attaches Idempotency-Key'
);

assert.match(
  modalSource,
  /adjustableConstBindings/,
  'manual execute modal must filter adjustable const bindings'
);
assert.match(
  modalSource,
  /param_overrides/,
  'manual execute modal must pass param_overrides through the trigger callback'
);
assert.match(
  modalSource,
  /trigger\(/,
  'manual execute modal must call the injected trigger callback'
);
assert.doesNotMatch(
  modalSource,
  /action_execution\/manual_trigger/,
  'manual execute modal must not call the raw manual_trigger URL'
);

console.log('alarm manual trigger idempotency test passed');
