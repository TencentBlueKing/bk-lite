import assert from 'node:assert/strict';
import test from 'node:test';

import { dispatchPageCommand, registerPageCommand, resetPageCommandsForTests } from '../registry';

test('dashboard apply custom event delivers the proposal payload', () => {
  resetPageCommandsForTests();
  let received: unknown;
  registerPageCommand('dashboard_config_apply', (value) => {
    received = value;
  });

  dispatchPageCommand({
    type: 'CUSTOM',
    name: 'dashboard_config_apply',
    value: { dashboardId: 'current', proposal: { schemaVersion: '1.0' } },
  });

  assert.deepEqual(received, {
    dashboardId: 'current',
    proposal: { schemaVersion: '1.0' },
  });
});
