import assert from 'node:assert/strict';
import path from 'node:path';
import ts from 'typescript';

import {
  deriveIMGroupView,
  getIMGroupPollDelay,
} from '../src/app/alarm/(pages)/incidents/components/collaboration/imGroup/state';
import {
  createIncidentIMGroupApi,
  type IncidentIMGroupHttpClient,
} from '../src/app/alarm/api/incidentIMGroup';
import type {
  CreateIncidentIMGroupParams,
  IncidentIMGroup,
  IncidentIMGroupOptions,
  IncidentIMMemberList,
  IncidentIMMemberListParams,
  UpdateIncidentIMGroupParams,
} from '../src/app/alarm/types/incidents';

const typeCheckedFiles = [
  'src/app/alarm/types/incidents.ts',
  'src/app/alarm/api/incidentIMGroup.ts',
  'src/app/alarm/api/incidents.ts',
  'src/app/alarm/(pages)/incidents/components/collaboration/imGroup/state.ts',
  'scripts/incident-im-group-ui-test.ts',
].map(filePath => path.resolve(filePath));
const tsconfig = ts.readConfigFile('tsconfig.json', ts.sys.readFile);
if (tsconfig.error) {
  throw new Error(ts.formatDiagnostic(tsconfig.error, {
    getCurrentDirectory: () => process.cwd(),
    getCanonicalFileName: fileName => fileName,
    getNewLine: () => '\n',
  }));
}
const parsedTsconfig = ts.parseJsonConfigFileContent(tsconfig.config, ts.sys, '.');
parsedTsconfig.options.noEmit = true;
parsedTsconfig.options.skipLibCheck = true;
parsedTsconfig.options.incremental = false;
delete parsedTsconfig.options.tsBuildInfoFile;
const typeCheckProgram = ts.createProgram(typeCheckedFiles, parsedTsconfig.options);
const typeCheckedFileSet = new Set(typeCheckedFiles);
const taskDiagnostics = ts.getPreEmitDiagnostics(typeCheckProgram).filter(diagnostic =>
  diagnostic.file && typeCheckedFileSet.has(path.resolve(diagnostic.file.fileName))
);
if (taskDiagnostics.length > 0) {
  throw new Error(ts.formatDiagnosticsWithColorAndContext(taskDiagnostics, {
    getCurrentDirectory: () => process.cwd(),
    getCanonicalFileName: fileName => fileName,
    getNewLine: () => '\n',
  }));
}

const groupContract = {
  id: '3c5d',
  provider: 'feishu',
  channel_id: 12,
  channel_name: 'Production Feishu',
  group_name: '[INC-001] Database connection error',
  external_chat_id: 'oc_xxx',
  open_chat_url: null,
  status: 'active_partial',
  current_stage: 'completed',
  status_message: '1 person is syncing',
  continuous_sync_enabled: true,
  pause_reason: null,
  member_summary: {
    total: 8,
    joined: 4,
    waiting: 2,
    failed: 1,
    unmapped: 1,
    conflict: 1,
    pending: 0,
    adding: 1,
  },
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
    updated_at: '2026-07-21T14:31:00+08:00',
  }],
} satisfies IncidentIMMemberList;

assert.equal(groupContract.channel_id, 12);
assert.equal(optionsContract.members[0].mapping_status, 'unmapped');
assert.equal(membersContract.items[0].sync_status, 'waiting');

assert.deepEqual(
  deriveIMGroupView({
    status: 'active_partial',
    pause_reason: null,
    member_summary: {
      total: 7,
      joined: 4,
      waiting: 2,
      failed: 1,
      unmapped: 1,
      conflict: 1,
      pending: 0,
      adding: 0,
    },
  }),
  { label: 'partial', primaryAction: 'retry', canPollFast: false },
);

assert.deepEqual(
  deriveIMGroupView({
    status: 'active',
    pause_reason: null,
    member_summary: {
      total: 3,
      joined: 1,
      waiting: 0,
      failed: 0,
      unmapped: 0,
      conflict: 0,
      pending: 1,
      adding: 1,
    },
  }),
  { label: 'active', primaryAction: 'open', canPollFast: true, syncingCount: 2 },
);
assert.deepEqual(
  deriveIMGroupView({
    status: 'active_partial',
    pause_reason: null,
    member_summary: {
      total: 5,
      joined: 2,
      waiting: 1,
      failed: 1,
      unmapped: 1,
      conflict: 0,
      pending: 0,
      adding: 1,
    },
  }),
  { label: 'partial', primaryAction: 'retry', canPollFast: true, syncingCount: 1 },
);

const stableSummary = {
  total: 2,
  joined: 2,
  waiting: 0,
  failed: 0,
  unmapped: 0,
  conflict: 0,
  pending: 0,
  adding: 0,
} as const;
assert.deepEqual(
  deriveIMGroupView({
    status: 'paused',
    pause_reason: 'manual',
    member_summary: stableSummary,
  }),
  { label: 'paused', primaryAction: 'resume', canPollFast: false },
);
assert.deepEqual(
  deriveIMGroupView({
    status: 'paused',
    pause_reason: 'incident_closed',
    member_summary: stableSummary,
  }),
  { label: 'incidentClosed', primaryAction: 'open', canPollFast: false },
);
assert.deepEqual(
  deriveIMGroupView({
    status: 'create_failed',
    pause_reason: null,
    member_summary: { ...stableSummary, joined: 0, failed: 2 },
  }),
  { label: 'createFailed', primaryAction: 'retry', canPollFast: false },
);
assert.deepEqual(
  deriveIMGroupView({
    status: 'degraded',
    pause_reason: null,
    member_summary: stableSummary,
  }),
  { label: 'degraded', primaryAction: 'retry', canPollFast: false },
);

const creatingView = deriveIMGroupView({
  status: 'creating',
  pause_reason: null,
  member_summary: stableSummary,
});
const activeSyncingView = deriveIMGroupView({
  status: 'active',
  pause_reason: null,
  member_summary: { ...stableSummary, total: 3, pending: 1 },
});
const partialSyncingView = deriveIMGroupView({
  status: 'active_partial',
  pause_reason: null,
  member_summary: { ...stableSummary, total: 3, adding: 1 },
});
const activeStableView = deriveIMGroupView({
  status: 'active',
  pause_reason: null,
  member_summary: stableSummary,
});

assert.equal(getIMGroupPollDelay(creatingView, 10_000, true), 2_000);
assert.equal(getIMGroupPollDelay(activeSyncingView, 29_999, true), 2_000);
assert.equal(getIMGroupPollDelay(partialSyncingView, 30_000, true), 5_000);
assert.equal(getIMGroupPollDelay(activeSyncingView, 40_000, true), 5_000);
assert.equal(getIMGroupPollDelay(activeStableView, 40_000, true), null);
assert.equal(getIMGroupPollDelay(activeSyncingView, 10_000, false), null);

interface RequestCall {
  verb: 'get' | 'post' | 'patch' | 'delete';
  url: string;
  data?: unknown;
  config?: unknown;
}

const calls: RequestCall[] = [];
const response = { marker: 'response' };
const fakeClient: IncidentIMGroupHttpClient = {
  get: async <T>(url: string, config?: unknown) => {
    calls.push({ verb: 'get', url, config });
    return response as T;
  },
  post: async <T>(url: string, data?: unknown, config?: unknown) => {
    calls.push({ verb: 'post', url, data, config });
    return response as T;
  },
  patch: async <T>(url: string, data?: unknown, config?: unknown) => {
    calls.push({ verb: 'patch', url, data, config });
    return response as T;
  },
  del: async <T>(url: string, config?: unknown) => {
    calls.push({ verb: 'delete', url, config });
    return response as T;
  },
};

const createParams: CreateIncidentIMGroupParams = {
  channel_id: 12,
  group_name: '[INC-001] Database connection error',
  owner_username: 'zhangsan',
  continuous_sync_enabled: true,
};
const updateParams: UpdateIncidentIMGroupParams = {
  continuous_sync_enabled: false,
};
const memberParams: IncidentIMMemberListParams = {
  filter: 'pending',
  page: 2,
  page_size: 50,
};

const runApiContractTests = async () => {
  const api = createIncidentIMGroupApi(fakeClient);
  assert.equal(await api.getIncidentIMGroup('42'), response);
  assert.equal(await api.getIncidentIMGroupOptions('42', 12), response);
  assert.equal(await api.createIncidentIMGroup('42', createParams), response);
  assert.equal(await api.updateIncidentIMGroup('42', updateParams), response);
  assert.equal(await api.getIncidentIMMembers('42', memberParams), response);
  assert.equal(await api.retryIncidentIMGroup('42'), response);
  assert.equal(await api.pauseIncidentIMGroup('42'), response);
  assert.equal(await api.resumeIncidentIMGroup('42'), response);
  assert.equal(await api.unlinkIncidentIMGroup('42', createParams.group_name), response);

  assert.deepEqual(calls, [
    { verb: 'get', url: '/alerts/api/incident/42/im-group/', config: undefined },
    {
      verb: 'get',
      url: '/alerts/api/incident/42/im-group/options/',
      config: { params: { channel_id: 12 } },
    },
    {
      verb: 'post',
      url: '/alerts/api/incident/42/im-group/',
      data: createParams,
      config: undefined,
    },
    {
      verb: 'patch',
      url: '/alerts/api/incident/42/im-group/',
      data: updateParams,
      config: undefined,
    },
    {
      verb: 'get',
      url: '/alerts/api/incident/42/im-group/members/',
      config: { params: memberParams },
    },
    {
      verb: 'post',
      url: '/alerts/api/incident/42/im-group/retry/',
      data: undefined,
      config: undefined,
    },
    {
      verb: 'post',
      url: '/alerts/api/incident/42/im-group/pause/',
      data: undefined,
      config: undefined,
    },
    {
      verb: 'post',
      url: '/alerts/api/incident/42/im-group/resume/',
      data: undefined,
      config: undefined,
    },
    {
      verb: 'delete',
      url: '/alerts/api/incident/42/im-group/',
      config: { data: { group_name: createParams.group_name } },
    },
  ]);
};

void runApiContractTests();
