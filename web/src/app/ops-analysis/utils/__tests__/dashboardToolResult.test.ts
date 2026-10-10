import assert from 'node:assert/strict';
import test from 'node:test';

import { claimToolCall, readDashboardApplyAction } from '../dashboardToolResult';

const proposal = {
  schemaVersion: '1.0',
  layout: [{ i: 'alarm-trend', valueConfig: { chartType: 'line', dataSource: 193 } }],
};

test('reads the apply action nested in a successful tool result', () => {
  const action = readDashboardApplyAction(JSON.stringify({
    success: true,
    data: {
      ok: true,
      proposal,
      pageAction: {
        name: 'dashboard_config_apply',
        value: { dashboardId: 'current', proposal },
      },
    },
  }));

  assert.equal(action?.dashboardId, 'current');
  assert.equal(action?.proposal.schemaVersion, '1.0');
});

test('ignores pending results and unrelated tool payloads', () => {
  assert.equal(readDashboardApplyAction(JSON.stringify({
    success: true,
    data: { ok: false, pending: [{ reason: 'required_param' }] },
  })), null);
  assert.equal(readDashboardApplyAction('not-json'), null);
  assert.equal(readDashboardApplyAction(JSON.stringify({
    pageAction: { name: 'other', value: { proposal } },
  })), null);
});

test('applies one tool call id once', () => {
  const seen = new Set<string>();
  assert.equal(claimToolCall(seen, 'call-1'), true);
  assert.equal(claimToolCall(seen, 'call-1'), false);
  assert.equal(claimToolCall(seen, ''), false);
});
