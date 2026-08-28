import * as assert from 'node:assert/strict';
import type { RecordRow } from '../src/app/system-manager/utils/userSyncPageUtils';
import { getUserSyncRunSummary } from '../src/app/system-manager/utils/userSyncPageUtils';

const messages: Record<string, string> = {
  'system.user.userSyncPage.runSummary.success': '同步成功：{{external}}；已同步 {{users}} 个用户、{{groups}} 个组织',
  'system.user.userSyncPage.runSummary.successWithLedger': '同步成功：{{external}}；{{users}}；{{groups}}',
  'system.user.userSyncPage.runSummary.partial': '部分成功：{{external}}；已同步 {{users}} 个用户、{{groups}} 个组织，{{conflicts}} 个冲突',
  'system.user.userSyncPage.runSummary.partialWithUsers': '部分成功：{{external}}；已同步 {{users}} 个用户、{{groups}} 个组织，{{conflicts}} 个冲突（冲突用户：{{usernames}}）',
  'system.user.userSyncPage.runSummary.partialWithLedger': '部分成功：{{external}}；{{users}}；{{groups}}',
  'system.user.userSyncPage.runSummary.partialWithLedgerAndUsers': '部分成功：{{external}}；{{users}}；{{groups}}（冲突用户：{{usernames}}）',
  'system.user.userSyncPage.runSummary.failed': '同步失败：{{external}}；{{reason}}',
  'system.user.userSyncPage.runSummary.failedConflict': '同步失败：{{external}}；已同步 {{users}} 个用户、{{groups}} 个组织，{{conflicts}} 个冲突用户（冲突用户：{{usernames}}）',
  'system.user.userSyncPage.runSummary.failedWithLedger': '同步失败：{{external}}；{{users}}；{{groups}}',
  'system.user.userSyncPage.runSummary.failedWithLedgerAndUsers': '同步失败：{{external}}；{{users}}；{{groups}}（冲突用户：{{usernames}}）',
  'system.user.userSyncPage.runSummary.withReason': '{{summary}}；{{reason}}',
  'system.user.userSyncPage.runSummary.userLedger': '用户：{{parts}}',
  'system.user.userSyncPage.runSummary.groupLedger': '组织：{{parts}}',
  'system.user.userSyncPage.runSummary.externalCounts': '外部用户共 {{users}} 人，外部组织共 {{groups}} 个',
  'system.user.userSyncPage.phaseCounter.syncUsersNew': '已新建 {{n}} 名用户',
  'system.user.userSyncPage.phaseCounter.syncUsersUpdated': '已更新 {{n}} 名用户',
  'system.user.userSyncPage.phaseCounter.syncUsersUnchanged': '无变化 {{n}} 名用户',
  'system.user.userSyncPage.phaseCounter.syncUsersConflict': '发现 {{n}} 名冲突用户',
  'system.user.userSyncPage.phaseCounter.syncUsersSkipped': '跳过无效 {{n}} 名用户',
  'system.user.userSyncPage.phaseCounter.syncGroupsCreated': '已新建 {{n}} 个组织',
  'system.user.userSyncPage.phaseCounter.syncGroupsUpdated': '已更新 {{n}} 个组织',
  'system.user.userSyncPage.phaseCounter.syncGroupsUnchanged': '无变化 {{n}} 个组织',
  'system.user.userSyncPage.phaseCounter.syncGroupsSkipped': '跳过无效 {{n}} 个组织',
  'system.user.userSyncPage.runSummary.result': '同步结果：{{external}}；{{summary}}',
  'system.user.userSyncPage.runSummary.withEmailStatus': '{{summary}}；{{email}}',
  'system.user.userSyncPage.runSummary.usernameListSeparator': '、',
  'system.user.userSyncPage.runSummary.emailSending': '初始密码邮件发送中（共 {{total}} 封）',
  'system.user.userSyncPage.runSummary.emailSent': '初始密码邮件已发送 {{sent}} 封',
  'system.user.userSyncPage.runSummary.emailPartialFailed': '初始密码邮件已发送 {{sent}} 封，发送失败 {{failed}} 封，请核查用户邮箱和邮件通道',
  'system.user.userSyncPage.runSummary.emailFailed': '初始密码邮件发送失败 {{failed}} 封，请核查用户邮箱和邮件通道',
};

const t = (key: string) => messages[key] ?? key;

const englishMessages: Record<string, string> = {
  'system.user.userSyncPage.runSummary.success': 'Sync succeeded: {{external}}; synced {{users}} users, {{groups}} groups',
  'system.user.userSyncPage.runSummary.successWithLedger': 'Sync succeeded: {{external}}; {{users}}; {{groups}}',
  'system.user.userSyncPage.runSummary.externalCounts': 'External users: {{users}}, external groups: {{groups}}',
  'system.user.userSyncPage.runSummary.emailSent': 'Initial password emails sent: {{sent}}',
  'system.user.userSyncPage.runSummary.result': 'Sync result: {{external}}; {{summary}}',
  'system.user.userSyncPage.runSummary.withEmailStatus': '{{summary}}; {{email}}',
  'system.user.userSyncPage.runSummary.usernameListSeparator': ', ',
  'system.user.userSyncPage.runSummary.userLedger': 'Users: {{parts}}',
  'system.user.userSyncPage.runSummary.groupLedger': 'Groups: {{parts}}',
  'system.user.userSyncPage.phaseCounter.syncUsersNew': 'Created {{n}} users',
  'system.user.userSyncPage.phaseCounter.syncUsersUpdated': 'Updated {{n}} users',
  'system.user.userSyncPage.phaseCounter.syncUsersUnchanged': '{{n}} users unchanged',
  'system.user.userSyncPage.phaseCounter.syncUsersConflict': 'Found {{n}} conflicting users',
  'system.user.userSyncPage.phaseCounter.syncUsersSkipped': 'Skipped {{n}} invalid users',
  'system.user.userSyncPage.phaseCounter.syncGroupsCreated': 'Created {{n}} groups',
  'system.user.userSyncPage.phaseCounter.syncGroupsUpdated': 'Updated {{n}} groups',
  'system.user.userSyncPage.phaseCounter.syncGroupsUnchanged': '{{n}} groups unchanged',
  'system.user.userSyncPage.phaseCounter.syncGroupsSkipped': 'Skipped {{n}} invalid groups',
};

const englishT = (key: string) => englishMessages[key] ?? key;

const successRecord: RecordRow = {
  id: 1,
  source: 1,
  source_name: '源A',
  trigger_mode: 'manual',
  status: 'success',
  request_id: 'req-1',
  summary: 'User sync completed: 1 users, 1 groups',
  synced_user_count: 1,
  synced_group_count: 1,
  disabled_user_count: 0,
  payload: { input_summary: { fetched_user_count: 1, fetched_group_count: 1 } },
  started_at: '2026-07-02T00:00:00Z',
  finished_at: '2026-07-02T00:01:00Z',
};

const partialRecord: RecordRow = {
  ...successRecord,
  id: 2,
  status: 'partial',
  synced_user_count: 1,
  synced_group_count: 1,
  payload: { input_summary: { fetched_user_count: 3, fetched_group_count: 1 }, conflict_user_count: 2, conflict_usernames: ['alice', 'bob'] },
};

const failedProviderRecord: RecordRow = {
  ...successRecord,
  id: 3,
  status: 'failed',
  synced_user_count: 0,
  synced_group_count: 0,
  payload: { input_summary: { fetched_user_count: 1, fetched_group_count: 0 }, errors: [{ message: 'Feishu access token request failed' }] },
};

const failedConflictRecord: RecordRow = {
  ...successRecord,
  id: 4,
  status: 'failed',
  synced_user_count: 0,
  synced_group_count: 1,
  payload: { input_summary: { fetched_user_count: 1, fetched_group_count: 1 }, conflict_user_count: 1, conflict_usernames: ['alice'] },
};

const emailSendingRecord: RecordRow = {
  ...successRecord,
  id: 5,
  payload: {
    ...successRecord.payload,
    email_status: { total: 2, sent: 0, failed: 0, completed: false },
  },
};

const emailSentRecord: RecordRow = {
  ...successRecord,
  id: 6,
  payload: {
    ...successRecord.payload,
    email_status: { total: 2, sent: 2, failed: 0, completed: true },
  },
};

const emailPartialFailedRecord: RecordRow = {
  ...successRecord,
  id: 7,
  payload: {
    ...successRecord.payload,
    email_status: { total: 2, sent: 1, failed: 1, completed: true },
  },
};

const emailFailedRecord: RecordRow = {
  ...successRecord,
  id: 8,
  payload: {
    ...successRecord.payload,
    email_status: { total: 2, sent: 0, failed: 2, completed: true },
  },
};

const runningRecord: RecordRow = {
  ...successRecord,
  id: 9,
  status: 'running',
};

const ledgerPartialRecord: RecordRow = {
  ...successRecord,
  id: 10,
  status: 'partial',
  synced_user_count: 3,
  synced_group_count: 10,
  payload: {
    input_summary: { fetched_user_count: 15, fetched_group_count: 10 },
    conflict_user_count: 12,
    conflict_usernames: ['alice', 'bob'],
    phase_progress: {
      sync_users: {
        current: 15,
        total: 15,
        status: 'finish',
        counters: { new_users: 0, updated_users: 0, unchanged_users: 3, skipped_invalid_users: 0, conflict_users: 12 },
      },
      sync_groups: {
        current: 10,
        total: 10,
        status: 'finish',
        counters: { created_groups: 6, updated_groups: 0, unchanged_groups: 4, skipped_invalid_groups: 0 },
      },
    },
  },
};

const failedLedgerRecord: RecordRow = {
  ...ledgerPartialRecord,
  id: 11,
  status: 'failed',
  synced_user_count: 0,
  payload: {
    ...ledgerPartialRecord.payload,
    errors: [{ message: 'directory unavailable' }],
  },
};

assert.equal(getUserSyncRunSummary(successRecord, t), '同步成功：外部用户共 1 人，外部组织共 1 个；已同步 1 个用户、1 个组织');
assert.equal(getUserSyncRunSummary(partialRecord, t), '部分成功：外部用户共 3 人，外部组织共 1 个；已同步 1 个用户、1 个组织，2 个冲突（冲突用户：alice、bob）');
assert.equal(
  getUserSyncRunSummary(ledgerPartialRecord, t),
  '部分成功：外部用户共 15 人，外部组织共 10 个；用户：无变化 3 名用户 · 发现 12 名冲突用户；组织：已新建 6 个组织 · 无变化 4 个组织（冲突用户：alice、bob）',
);
assert.equal(getUserSyncRunSummary(failedProviderRecord, t), '同步失败：外部用户共 1 人，外部组织共 0 个；Feishu access token request failed');
assert.equal(
  getUserSyncRunSummary(failedLedgerRecord, t),
  '同步失败：外部用户共 15 人，外部组织共 10 个；用户：无变化 3 名用户 · 发现 12 名冲突用户；组织：已新建 6 个组织 · 无变化 4 个组织（冲突用户：alice、bob）；directory unavailable',
);
assert.equal(getUserSyncRunSummary(failedConflictRecord, t), '同步失败：外部用户共 1 人，外部组织共 1 个；已同步 0 个用户、1 个组织，1 个冲突用户（冲突用户：alice）');
assert.equal(getUserSyncRunSummary(emailSendingRecord, t), '同步成功：外部用户共 1 人，外部组织共 1 个；已同步 1 个用户、1 个组织；初始密码邮件发送中（共 2 封）');
assert.equal(getUserSyncRunSummary(emailSentRecord, t), '同步成功：外部用户共 1 人，外部组织共 1 个；已同步 1 个用户、1 个组织；初始密码邮件已发送 2 封');
assert.equal(getUserSyncRunSummary(emailPartialFailedRecord, t), '同步成功：外部用户共 1 人，外部组织共 1 个；已同步 1 个用户、1 个组织；初始密码邮件已发送 1 封，发送失败 1 封，请核查用户邮箱和邮件通道');
assert.equal(getUserSyncRunSummary(emailFailedRecord, t), '同步成功：外部用户共 1 人，外部组织共 1 个；已同步 1 个用户、1 个组织；初始密码邮件发送失败 2 封，请核查用户邮箱和邮件通道');
assert.equal(getUserSyncRunSummary(runningRecord, englishT), 'Sync result: External users: 1, external groups: 1; User sync completed: 1 users, 1 groups');
assert.equal(getUserSyncRunSummary(emailSentRecord, englishT), 'Sync succeeded: External users: 1, external groups: 1; synced 1 users, 1 groups; Initial password emails sent: 2');

console.log('user sync record summary tests passed');
