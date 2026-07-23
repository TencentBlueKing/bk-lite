import assert from 'node:assert/strict';
import fs from 'node:fs';
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
import {
  canSubmitIMGroupCreation,
  createPollScheduler,
  createRequestGate,
  getInitialMemberFilter,
  isChannelOptionsCurrent,
  ownsIMGroupResponse,
  probeCreatePermission,
  resolveMemberQueryVisibility,
  runIMGroupAction,
  settleMemberDrawerRequest,
  shouldInitializeCreateForm,
} from '../src/app/alarm/(pages)/incidents/components/collaboration/imGroup/controller';
import {
  deriveCreateModalModel,
  deriveMemberDrawerModel,
  derivePanelModel,
} from '../src/app/alarm/(pages)/incidents/components/collaboration/imGroup/viewModel';
import type {
  CreateIncidentIMGroupParams,
  IncidentIMGroup,
  IncidentIMGroupOptions,
  IncidentIMMemberList,
  IncidentIMMemberListParams,
  UpdateIncidentIMGroupParams,
} from '../src/app/alarm/types/incidents';

const task10Files = [
  'src/app/alarm/(pages)/incidents/components/collaboration/imGroup/controller.ts',
  'src/app/alarm/(pages)/incidents/components/collaboration/imGroup/useIncidentIMGroup.ts',
  'src/app/alarm/(pages)/incidents/components/collaboration/imGroup/viewModel.ts',
  'src/app/alarm/(pages)/incidents/components/collaboration/imGroup/createModal.tsx',
  'src/app/alarm/(pages)/incidents/components/collaboration/imGroup/memberDrawer.tsx',
  'src/app/alarm/(pages)/incidents/components/collaboration/imGroup/confirmModals.tsx',
  'src/app/alarm/(pages)/incidents/components/collaboration/imGroup/index.tsx',
] as const;

const typeCheckedFiles = [
  'src/app/alarm/types/incidents.ts',
  'src/app/alarm/api/incidentIMGroup.ts',
  'src/app/alarm/api/incidents.ts',
  'src/app/alarm/(pages)/incidents/components/collaboration/imGroup/state.ts',
  'src/app/alarm/(pages)/incidents/components/collaboration/index.tsx',
  'scripts/incident-im-group-ui-test.ts',
  ...task10Files,
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
  can_create: true,
  preferred_owner_username: 'zhangsan',
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
const probeFailure = new Error('forbidden');

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
  const signal = new AbortController().signal;
  assert.equal(await api.getIncidentIMGroup('42', signal), response);
  assert.equal(await api.getIncidentIMGroupOptions('42', 12, signal), response);
  assert.equal(await api.createIncidentIMGroup('42', createParams), response);
  assert.equal(await api.updateIncidentIMGroup('42', updateParams), response);
  assert.equal(await api.getIncidentIMMembers('42', memberParams, signal), response);
  assert.equal(await api.retryIncidentIMGroup('42'), response);
  assert.equal(await api.retryIncidentIMGroup('42', 'lisi'), response);
  assert.equal(await api.pauseIncidentIMGroup('42'), response);
  assert.equal(await api.resumeIncidentIMGroup('42'), response);
  assert.equal(await api.unlinkIncidentIMGroup('42', createParams.group_name), response);

  assert.deepEqual(calls, [
    { verb: 'get', url: '/alerts/api/incident/42/im-group/', config: { signal } },
    {
      verb: 'get',
      url: '/alerts/api/incident/42/im-group/options/',
      config: { params: { channel_id: 12 }, signal },
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
      config: { params: memberParams, signal },
    },
    {
      verb: 'post',
      url: '/alerts/api/incident/42/im-group/retry/',
      data: undefined,
      config: undefined,
    },
    {
      verb: 'post',
      url: '/alerts/api/incident/42/im-group/retry/',
      data: { username: 'lisi' },
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

const scheduled = new Map<number, () => void>();
const cleared: number[] = [];
let nextTimerId = 0;
const scheduler = createPollScheduler({
  setTimer: callback => {
    nextTimerId += 1;
    scheduled.set(nextTimerId, callback);
    return nextTimerId;
  },
  clearTimer: timerId => {
    cleared.push(timerId);
    scheduled.delete(timerId);
  },
});
scheduler.schedule(() => undefined, 2_000);
scheduler.schedule(() => undefined, 5_000);
assert.deepEqual(cleared, [1], 'a second schedule must replace the prior timer');
assert.equal(scheduled.size, 1, 'only one IM group poll timer may remain');
scheduler.stop();
assert.deepEqual(cleared, [1, 2]);
assert.equal(scheduled.size, 0);

assert.equal(ownsIMGroupResponse('42', '42', 'g1', 'g1'), true);
assert.equal(ownsIMGroupResponse('42', '42', null, null), true);
assert.equal(
  ownsIMGroupResponse('42', '42', 'new-group', null),
  false,
  'an old no-group response must not overwrite a group created while it was in flight',
);
assert.equal(ownsIMGroupResponse('43', '42', 'g1', 'g1'), false);
assert.equal(ownsIMGroupResponse('42', '42', 'g2', 'g1'), false);
assert.equal(getInitialMemberFilter(2), 'pending');
assert.equal(getInitialMemberFilter(0), 'all');
assert.deepEqual(
  resolveMemberQueryVisibility(
    false,
    true,
    { filter: 'joined', page: 4, pageSize: 50 },
    2,
  ),
  { filter: 'pending', page: 1, pageSize: 20 },
);
assert.deepEqual(
  resolveMemberQueryVisibility(
    true,
    true,
    { filter: 'joined', page: 4, pageSize: 50 },
    3,
  ),
  { filter: 'joined', page: 4, pageSize: 50 },
  'an open drawer must preserve its filter and page while group summaries refresh',
);
assert.equal(canSubmitIMGroupCreation(optionsContract, 12, 'Incident room', 'zhangsan'), true);
assert.equal(canSubmitIMGroupCreation(optionsContract, 12, 'Incident room', undefined), false);
assert.equal(isChannelOptionsCurrent(12, 12), true);
assert.equal(isChannelOptionsCurrent(13, 12), false);
assert.equal(shouldInitializeCreateForm(false, true), true);
assert.equal(
  shouldInitializeCreateForm(true, true),
  false,
  'an options response while open must not reset the user-selected channel',
);

assert.deepEqual(
  deriveCreateModalModel({
    selectedChannelId: 12,
    resolvedChannelId: 12,
    options: {
      ...optionsContract,
      can_create: true,
      preferred_owner_username: 'zhangsan',
    },
    previewError: null,
  }),
  {
    contextual: true,
    ownerCandidates: optionsContract.owner_candidates,
    defaultOwnerUsername: 'zhangsan',
    showPreviewError: false,
    canCreate: true,
  },
);
assert.deepEqual(
  deriveCreateModalModel({
    selectedChannelId: 13,
    resolvedChannelId: 12,
    options: {
      ...optionsContract,
      can_create: true,
      preferred_owner_username: 'not-a-candidate',
    },
    previewError: probeFailure,
  }),
  {
    contextual: false,
    ownerCandidates: [],
    defaultOwnerUsername: null,
    showPreviewError: true,
    canCreate: false,
  },
);

assert.deepEqual(
  deriveMemberDrawerModel(groupContract, null),
  {
    phase: 'members',
    statusLabel: 'partial',
    continuousSyncEnabled: true,
    lastSyncAt: groupContract.last_sync_at,
    showMemberError: false,
    canRetryPending: true,
    showMappingRepair: true,
  },
);
assert.deepEqual(
  deriveMemberDrawerModel(
    { ...groupContract, status: 'create_failed', current_stage: 'completed' },
    probeFailure,
  ),
  {
    phase: 'progress',
    statusLabel: 'createFailed',
    continuousSyncEnabled: true,
    lastSyncAt: groupContract.last_sync_at,
    showMemberError: false,
    canRetryPending: false,
    showMappingRepair: false,
  },
);

assert.deepEqual(
  derivePanelModel({
    group: null,
    groupLoading: false,
    groupError: false,
    optionsLoading: false,
    optionsError: null,
    options: {
      channels: [],
      default_group_name: 'Incident group',
      can_create: false,
      preferred_owner_username: null,
    },
  }),
  {
    state: 'empty',
    canCreate: false,
    showPermissionError: false,
    primaryAction: null,
    sidebarClassName: 'w-full lg:w-[220px]',
  },
);
assert.deepEqual(
  derivePanelModel({
    group: groupContract,
    groupLoading: false,
    groupError: false,
    optionsLoading: false,
    optionsError: null,
    options: null,
  }),
  {
    state: 'group',
    canCreate: false,
    showPermissionError: false,
    primaryAction: 'retry',
    sidebarClassName: 'w-full lg:w-[220px]',
  },
);

const requestGate = createRequestGate();
const firstGroupRequest = requestGate.begin('group');
const secondGroupRequest = requestGate.begin('group');
assert.equal(firstGroupRequest.signal.aborted, true, 'new group request must abort the prior request');
assert.equal(requestGate.finish(firstGroupRequest), false, 'old requests cannot clear current loading');
assert.equal(requestGate.isCurrent(secondGroupRequest), true);
assert.equal(requestGate.finish(secondGroupRequest), true);
const optionRequest = requestGate.begin('options');
const memberRequest = requestGate.begin('members');
requestGate.abortAll();
assert.equal(optionRequest.signal.aborted, true);
assert.equal(memberRequest.signal.aborted, true);


assert.deepEqual(
  settleMemberDrawerRequest(
    { data: membersContract, error: null },
    { error: new Error('member request failed') },
  ),
  {
    data: { count: 0, items: [] },
    error: new Error('member request failed'),
  },
);
assert.deepEqual(
  settleMemberDrawerRequest(
    { data: { count: 0, items: [] }, error: probeFailure },
    { data: membersContract },
  ),
  { data: membersContract, error: null },
);

const runControllerAsyncTests = async () => {
  const emptyPermissionProbe = await probeCreatePermission(async () => ({
    channels: [],
    default_group_name: 'Incident group',
    can_create: false,
    preferred_owner_username: null,
  }));
  assert.deepEqual(emptyPermissionProbe, {
    canCreate: false,
    options: {
      channels: [],
      default_group_name: 'Incident group',
      can_create: false,
      preferred_owner_username: null,
    },
    error: null,
  });
  assert.deepEqual(
    await probeCreatePermission(async () => { throw probeFailure; }),
    { canCreate: false, options: null, error: probeFailure },
  );

  let actionSucceeded = 0;
  let actionFailed: unknown = null;
  assert.equal(
    await runIMGroupAction(
      async () => undefined,
      () => { actionSucceeded += 1; },
      error => { actionFailed = error; },
    ),
    true,
  );
  assert.equal(actionSucceeded, 1);
  assert.equal(actionFailed, null);
  const actionError = new Error('action failed');
  assert.equal(
    await runIMGroupAction(
      async () => { throw actionError; },
      () => { actionSucceeded += 1; },
      error => { actionFailed = error; },
    ),
    false,
  );
  assert.equal(actionSucceeded, 1);
  assert.equal(actionFailed, actionError);
};
void runControllerAsyncTests();

for (const filePath of task10Files) {
  assert.equal(fs.existsSync(filePath), true, `missing Task 10 file: ${filePath}`);
}

const parseSource = (filePath: string) =>
  ts.createSourceFile(
    filePath,
    fs.readFileSync(filePath, 'utf8'),
    ts.ScriptTarget.Latest,
    true,
    filePath.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );

const collaborationSource = parseSource(
  'src/app/alarm/(pages)/incidents/components/collaboration/index.tsx',
);
const collaborationText = collaborationSource.getFullText();
const panelPosition = collaborationText.indexOf('<IncidentIMGroupPanel');
const collaboratorsHeadingPosition = collaborationText.indexOf("t('incidents.collaborators')");
assert.ok(panelPosition >= 0, 'collaboration sidebar must render IncidentIMGroupPanel');
assert.ok(
  panelPosition < collaboratorsHeadingPosition,
  'IncidentIMGroupPanel must be rendered before the collaborators heading',
);
assert.match(collaborationText, /refreshVersion=\{imGroupRefreshVersion\}/);
assert.match(collaborationText, /removeCollaboratorWarning/);

const createModalPath = task10Files.find(filePath => filePath.endsWith('/createModal.tsx'));
assert.ok(createModalPath);
const createModalText = parseSource(createModalPath).getFullText();
for (const field of ['channel_id', 'group_name', 'owner_username', 'continuous_sync_enabled']) {
  assert.ok(createModalText.includes(field), `create modal must own ${field}`);
}
assert.match(createModalText, /width=\{600\}/);
assert.match(createModalText, /calc\(100vh - 240px\)/);

const memberDrawerPath = task10Files.find(filePath => filePath.endsWith('/memberDrawer.tsx'));
assert.ok(memberDrawerPath);
const memberDrawerText = parseSource(memberDrawerPath).getFullText();
assert.match(memberDrawerText, /getIncidentIMMembers/);
assert.match(memberDrawerText, /pageSize:\s*20/);
assert.match(memberDrawerText, /min\(720px,\s*100vw\)/);
assert.match(memberDrawerText, /onRetry\(member\.username\)/);
assert.match(memberDrawerText, /onRetry\(\)/);

const hookPath = task10Files.find(filePath => filePath.endsWith('/useIncidentIMGroup.ts'));
assert.ok(hookPath);
const hookText = parseSource(hookPath).getFullText();
assert.match(hookText, /AbortController/);
assert.match(hookText, /visibilitychange/);
assert.match(hookText, /focus/);
assert.match(hookText, /refreshVersion/);

const zh = JSON.parse(fs.readFileSync('src/app/alarm/locales/zh.json', 'utf8')) as unknown;
const en = JSON.parse(fs.readFileSync('src/app/alarm/locales/en.json', 'utf8')) as unknown;
const getNested = (root: unknown, keyPath: string): unknown =>
  keyPath.split('.').reduce<unknown>((value, key) => {
    if (typeof value !== 'object' || value === null || !(key in value)) return undefined;
    return (value as Record<string, unknown>)[key];
  }, root);
const localeKeys = [
  'incidents.imGroup.title',
  'incidents.imGroup.create',
  'incidents.imGroup.creating',
  'incidents.imGroup.active',
  'incidents.imGroup.partial',
  'incidents.imGroup.paused',
  'incidents.imGroup.incidentClosed',
  'incidents.imGroup.createFailed',
  'incidents.imGroup.degraded',
  'incidents.imGroup.viewDetails',
  'incidents.imGroup.retry',
  'incidents.imGroup.unlinkConfirm',
  'incidents.imGroup.removeCollaboratorWarning',
] as const;
for (const key of localeKeys) {
  assert.equal(typeof getNested(zh, key), 'string', `missing zh.${key}`);
  assert.equal(typeof getNested(en, key), 'string', `missing en.${key}`);
}

const collectLeafKeys = (value: unknown, prefix = ''): string[] => {
  if (typeof value !== 'object' || value === null) return [prefix];
  return Object.entries(value as Record<string, unknown>)
    .flatMap(([key, child]) => collectLeafKeys(child, prefix ? `${prefix}.${key}` : key))
    .sort();
};
assert.deepEqual(
  collectLeafKeys(getNested(zh, 'incidents.imGroup')),
  collectLeafKeys(getNested(en, 'incidents.imGroup')),
  'Chinese and English IM group locale keys must stay aligned',
);

for (const filePath of task10Files) {
  const source = parseSource(filePath);
  assert.doesNotMatch(source.getFullText(), /#[0-9a-f]{3,8}\b/i, `${filePath} contains a hard-coded color`);
  const anyNodes: ts.Node[] = [];
  const visit = (node: ts.Node) => {
    if (node.kind === ts.SyntaxKind.AnyKeyword) anyNodes.push(node);
    ts.forEachChild(node, visit);
  };
  visit(source);
  assert.equal(anyNodes.length, 0, `${filePath} must not add explicit any types`);
}
