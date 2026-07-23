import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
  deriveIMGroupView,
  getIMGroupPollDelay,
} from '../src/app/alarm/(pages)/incidents/components/collaboration/imGroup/state';
import type {
  IncidentIMGroup,
  IncidentIMGroupOptions,
  IncidentIMMemberList,
} from '../src/app/alarm/types/incidents';

const groupContract = {
  id: '3c5d',
  channel_id: 12,
  channel_name: 'Production Feishu',
  group_name: '[INC-001] Database connection error',
  status: 'active_partial',
  current_stage: 'completed',
  continuous_sync_enabled: true,
  pause_reason: null,
  member_summary: { total: 7, joined: 4, waiting: 2, failed: 1 },
  permissions: {
    can_manage: true,
    can_retry: true,
    can_pause: true,
    can_resume: false,
    can_unlink: true,
  },
  last_sync_at: '2026-07-21T14:32:00+08:00',
} satisfies IncidentIMGroup;

const optionsContract = {
  channels: [{ id: 12, name: 'Production Feishu' }],
  default_group_name: '[INC-001] Database connection error',
  members: [{
    username: 'lisi',
    display_name: 'Li Si',
    role: 'collaborator',
    mapping_status: 'unmapped',
    error_code: 'IM_USER_UNMAPPED',
    error_message: 'User mapping is missing',
  }],
  owner_candidates: [{ username: 'zhangsan', display_name: 'Zhang San' }],
} satisfies IncidentIMGroupOptions;

const membersContract = {
  count: 1,
  items: [{
    username: 'lisi',
    display_name: 'Li Si',
    role: 'collaborator',
    mapping_status: 'unmapped',
    sync_status: 'waiting',
    error_code: 'IM_USER_UNMAPPED',
    error_message: 'User mapping is missing',
  }],
} satisfies IncidentIMMemberList;

assert.equal(groupContract.channel_id, 12);
assert.equal(optionsContract.members[0].mapping_status, 'unmapped');
assert.equal(membersContract.items[0].sync_status, 'waiting');

const incidentsApiSource = readFileSync(
  fileURLToPath(new URL('../src/app/alarm/api/incidents.ts', import.meta.url)),
  'utf8',
);
for (const methodName of [
  'getIncidentIMGroup',
  'getIncidentIMGroupOptions',
  'createIncidentIMGroup',
  'updateIncidentIMGroup',
  'getIncidentIMMembers',
  'retryIncidentIMGroup',
  'pauseIncidentIMGroup',
  'resumeIncidentIMGroup',
  'unlinkIncidentIMGroup',
]) {
  assert.match(incidentsApiSource, new RegExp(`\\b${methodName}\\b`), `missing API method ${methodName}`);
}
assert.match(
  incidentsApiSource,
  /del<void>\(`\/alerts\/api\/incident\/\$\{incidentPk\}\/im-group\/`,[\s\S]*?data:\s*\{\s*group_name:\s*groupName\s*\}/,
  'unlink must send group_name as the DELETE request body',
);

assert.deepEqual(
  deriveIMGroupView({
    status: 'active_partial',
    pause_reason: null,
    member_summary: { total: 7, joined: 4, waiting: 2, failed: 1 },
  }),
  { label: 'partial', primaryAction: 'retry', canPollFast: false },
);

assert.deepEqual(
  deriveIMGroupView({
    status: 'active',
    pause_reason: null,
    member_summary: { total: 3, joined: 1, waiting: 0, failed: 0 },
  }),
  { label: 'active', primaryAction: 'open', canPollFast: true, syncingCount: 2 },
);
assert.deepEqual(
  deriveIMGroupView({
    status: 'active_partial',
    pause_reason: null,
    member_summary: { total: 5, joined: 2, waiting: 1, failed: 1 },
  }),
  { label: 'partial', primaryAction: 'retry', canPollFast: true, syncingCount: 1 },
);

assert.deepEqual(
  deriveIMGroupView({
    status: 'paused',
    pause_reason: 'manual',
    member_summary: { total: 2, joined: 2, waiting: 0, failed: 0 },
  }),
  { label: 'paused', primaryAction: 'resume', canPollFast: false },
);
assert.deepEqual(
  deriveIMGroupView({
    status: 'paused',
    pause_reason: 'incident_closed',
    member_summary: { total: 2, joined: 2, waiting: 0, failed: 0 },
  }),
  { label: 'incidentClosed', primaryAction: 'open', canPollFast: false },
);
assert.deepEqual(
  deriveIMGroupView({
    status: 'create_failed',
    pause_reason: null,
    member_summary: { total: 2, joined: 0, waiting: 0, failed: 2 },
  }),
  { label: 'createFailed', primaryAction: 'retry', canPollFast: false },
);
assert.deepEqual(
  deriveIMGroupView({
    status: 'degraded',
    pause_reason: null,
    member_summary: { total: 2, joined: 2, waiting: 0, failed: 0 },
  }),
  { label: 'degraded', primaryAction: 'retry', canPollFast: false },
);

assert.equal(getIMGroupPollDelay('pending_create', 0, true), 2_000);
assert.equal(getIMGroupPollDelay('creating', 10_000, true), 2_000);
assert.equal(getIMGroupPollDelay('creating', 29_999, true), 2_000);
assert.equal(getIMGroupPollDelay('creating', 30_000, true), 5_000);
assert.equal(getIMGroupPollDelay('creating', 40_000, true), 5_000);
assert.equal(getIMGroupPollDelay('active', 40_000, true), null);
assert.equal(getIMGroupPollDelay('creating', 10_000, false), null);
