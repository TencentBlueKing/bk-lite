import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import type { UserSyncRunProgressPayload } from '../src/app/system-manager/types/user-sync';
import {
  calcPercent,
  formatPhaseProgressMeta,
  formatPhaseErrorMessage,
  formatUserSyncErrorMessage,
  formatPhaseBusinessResult,
  formatEmailNotificationResult,
  formatElapsed,
  formatPhaseCounterLine,
  shouldExpandPhase,
  getPhaseLabel,
  getPhaseDisplayStatus,
  getPhaseDisplayProgress,
  getPhasesForRun,
  getPhaseStatusConfig,
  safeGetPhaseProgress,
} from '../src/app/system-manager/utils/userSyncProgress';

// /api/locales 用 flattenMessages 把嵌套 JSON 展平为点号路径,
// 所以 mock 也用全路径 key(与生产一致)
const messages: Record<string, string> = {
  'system.user.userSyncPage.phase.fetchDirectory': '拉取目录',
  'system.user.userSyncPage.phase.syncGroups': '同步组织',
  'system.user.userSyncPage.phase.syncUsers': '同步用户',
  'system.user.userSyncPage.phase.reconcile': '清理失效对象',
  'system.user.userSyncPage.phase.finalize': '初始密码通知',
  'system.user.userSyncPage.phaseStatus.wait': '等待',
  'system.user.userSyncPage.phaseStatus.process': '进行中',
  'system.user.userSyncPage.phaseStatus.finish': '已完成',
  'system.user.userSyncPage.phaseStatus.error': '失败',
  'system.user.userSyncPage.phaseStatus.skipped': '已跳过',
  'system.user.userSyncPage.phaseCounter.syncUsersNew': '已新建 {{n}} 名用户',
  'system.user.userSyncPage.phaseCounter.syncUsersUpdated': '已更新 {{n}} 名用户',
  'system.user.userSyncPage.phaseCounter.syncUsersConflict': '发现 {{n}} 名冲突用户',
  'system.user.userSyncPage.phaseCounter.reconcileDisabled': '禁用 {{n}}',
  'system.user.userSyncPage.phaseCounter.reconcileDeleted': '删除 {{n}} 组',
  'system.user.userSyncPage.phaseCounter.syncGroupsCreated': '已新建 {{n}} 个组织',
  'system.user.userSyncPage.phaseCounter.syncGroupsUpdated': '已更新 {{n}} 个组织',
  'system.user.userSyncPage.progressDrawer.elapsed': '耗时 {{duration}}',
  'system.user.userSyncPage.progressDrawer.processed': '已处理 {{current}} / {{total}}',
  'system.user.userSyncPage.phaseResult.fetchDirectory': '已获取 {{users}} 名用户 · {{groups}} 个组织',
  'system.user.userSyncPage.phaseResult.syncGroupsUnchanged': '已核验 {{groups}} 个组织，未发现变更',
  'system.user.userSyncPage.phaseResult.syncUsersUnchanged': '已核验 {{users}} 名用户，未发现变更',
  'system.user.userSyncPage.phaseResult.reconcileChanged': '已禁用 {{users}} 名用户 · 已移除 {{groups}} 个组织',
  'system.user.userSyncPage.phaseResult.reconcileUnchanged': '未发现需清理的用户或组织',
  'system.user.userSyncPage.phaseResult.emailQueued': '邮件已入队，待发送 {{total}} 封',
  'system.user.userSyncPage.phaseResult.emailSending': '邮件发送中，已发送 {{sent}} / {{total}} 封',
  'system.user.userSyncPage.phaseResult.emailCompleted': '邮件已完成，成功 {{sent}} 封',
  'system.user.userSyncPage.phaseResult.emailFailed': '邮件发送失败 {{failed}} 封',
  'system.user.userSyncPage.phaseResult.emailSkippedNoNewUsers': '本次未新建用户，无需发送初始密码通知',
  'system.user.userSyncPage.phaseError.syncFailed': '同步失败，请稍后重试或联系管理员',
  'system.user.userSyncPage.phaseError.providerFetchFailed': '目录拉取失败，请检查同步源配置和连接状态',
  'system.user.userSyncPage.phaseError.emailEnqueueFailed': '初始密码邮件任务入队失败，请稍后重试',
};
// 严格 t():无 defaultMessage,缺失 key 直接返回 key,符合生产行为
const t = (key: string, fallback?: string) => {
  const v = messages[key];
  return v ?? fallback ?? key;
};

// --- getPhasesForRun ---

function testGetPhasesForRun() {
  // mode=null → 4 阶段
  assert.deepStrictEqual(
    getPhasesForRun({} as UserSyncRunProgressPayload),
    ['fetch_directory', 'sync_groups', 'sync_users', 'reconcile'],
  );
  // mode=none → 4 阶段
  assert.deepStrictEqual(
    getPhasesForRun({ password_init_mode: 'none' } as UserSyncRunProgressPayload),
    ['fetch_directory', 'sync_groups', 'sync_users', 'reconcile'],
  );
  // mode=uniform → 5 阶段
  assert.deepStrictEqual(
    getPhasesForRun({ password_init_mode: 'uniform' } as UserSyncRunProgressPayload),
    ['fetch_directory', 'sync_groups', 'sync_users', 'reconcile', 'finalize'],
  );
  // mode=random → 5 阶段
  assert.deepStrictEqual(
    getPhasesForRun({ password_init_mode: 'random' } as UserSyncRunProgressPayload),
    ['fetch_directory', 'sync_groups', 'sync_users', 'reconcile', 'finalize'],
  );
  // null payload → 4 阶段(默认)
  assert.deepStrictEqual(getPhasesForRun(null), ['fetch_directory', 'sync_groups', 'sync_users', 'reconcile']);
  assert.deepStrictEqual(getPhasesForRun(undefined), ['fetch_directory', 'sync_groups', 'sync_users', 'reconcile']);
  console.log('  ✓ getPhasesForRun');
}

// --- getPhaseStatusConfig ---

function testGetPhaseStatusConfig() {
  const finish = getPhaseStatusConfig('finish', t);
  assert.equal(finish.tagColor, 'success');
  assert.equal(finish.stepStatus, 'finish');
  assert.equal(finish.icon, 'check');

  const process = getPhaseStatusConfig('process', t);
  assert.equal(process.tagColor, 'processing');
  assert.equal(process.stepStatus, 'process');
  assert.equal(process.icon, 'loading');

  const error = getPhaseStatusConfig('error', t);
  assert.equal(error.tagColor, 'error');
  assert.equal(error.stepStatus, 'error');
  assert.equal(error.icon, 'close');

  const skipped = getPhaseStatusConfig('skipped', t);
  assert.equal(skipped.tagColor, 'default');
  assert.equal(skipped.icon, 'minus');

  const wait = getPhaseStatusConfig('wait', t);
  assert.equal(wait.tagColor, 'default');
  assert.equal(wait.stepStatus, 'wait');
  assert.equal(wait.icon, 'clock');

  // 未知状态回退到 wait
  const unknown = getPhaseStatusConfig('xyz' as unknown as 'wait', t);
  assert.equal(unknown.stepStatus, 'wait');
  console.log('  ✓ getPhaseStatusConfig');
}

// --- getPhaseLabel ---

function testGetPhaseLabel() {
  assert.equal(getPhaseLabel('fetch_directory', t), '拉取目录');
  assert.equal(getPhaseLabel('sync_groups', t), '同步组织');
  assert.equal(getPhaseLabel('sync_users', t), '同步用户');
  assert.equal(getPhaseLabel('reconcile', t), '清理失效对象');
  assert.equal(getPhaseLabel('finalize', t), '初始密码通知');
  console.log('  ✓ getPhaseLabel');
}

function testPhaseLabelsInLocales() {
  const zh = JSON.parse(readFileSync('src/app/system-manager/locales/zh.json', 'utf8'));
  const en = JSON.parse(readFileSync('src/app/system-manager/locales/en.json', 'utf8'));
  assert.equal(zh.system.user.userSyncPage.phase.reconcile, '清理失效对象');
  assert.equal(en.system.user.userSyncPage.phase.reconcile, 'Clean Inactive Objects');
  console.log('  ✓ phase labels in locales');
}

function testDrawerVisualHierarchy() {
  const component = readFileSync(
    'src/app/system-manager/components/user/user-sync/UserSyncRunProgressDrawer.tsx',
    'utf8',
  );
  const styles = readFileSync(
    'src/app/system-manager/components/user/user-sync/UserSyncRunProgressDrawer.module.scss',
    'utf8',
  );
  assert.match(component, /className=\{styles\.headerLine\}/);
  assert.match(component, /run\?\.source_name \?\? t\('system\.user\.userSyncPage\.progressDrawer\.title'\)/);
  assert.doesNotMatch(component, /progressDrawer\.summary/);
  assert.match(component, /run\.finished_at &&\s*\([\s\S]*?formatElapsed\(run\.started_at, run\.finished_at, t\)/);
  assert.doesNotMatch(component, /request_id/);
  assert.doesNotMatch(component, /isStrongPhaseStatus/);
  assert.match(component, /<Tag bordered=\{false\} color=\{config\.tagColor\} className=\{styles\.phaseStatus\}>/);
  assert.match(styles, /\.phaseResult\s*\{[\s\S]*?color: var\(--color-text-1\)/);
  assert.match(styles, /\.phaseTimestamp\s*\{[\s\S]*?color: var\(--color-text-3\)/);
  console.log('  ✓ drawer visual hierarchy');
}

// --- formatPhaseCounterLine ---

function testFormatPhaseCounterLine() {
  // sync_users: 5 新建 / 3 更新 / 1 冲突
  const syncPayload: UserSyncRunProgressPayload = {
    phase_progress: {
      sync_users: {
        current: 9, total: 9, status: 'finish',
        counters: { new_users: 5, updated_users: 3, conflict_users: 1 },
      },
    },
  };
  assert.equal(
    formatPhaseCounterLine('sync_users', syncPayload, t),
    '已新建 5 名用户 · 已更新 3 名用户 · 发现 1 名冲突用户',
  );

  // sync_users 全 0 → 空串(不显示多余行)
  const zeroPayload: UserSyncRunProgressPayload = {
    phase_progress: {
      sync_users: { current: 0, total: 0, status: 'finish', counters: { new_users: 0, updated_users: 0, conflict_users: 0 } },
    },
  };
  assert.equal(formatPhaseCounterLine('sync_users', zeroPayload, t), '');

  // reconcile: 2 禁用 / 1 删除
  const reconcilePayload: UserSyncRunProgressPayload = {
    phase_progress: {
      reconcile: { current: 1, total: 1, status: 'finish', counters: { disabled_users: 2, deleted_group_count: 1 } },
    },
  };
  assert.equal(formatPhaseCounterLine('reconcile', reconcilePayload, t), '禁用 2 · 删除 1 组');

  // reconcile 只有 disabled 没有 deleted
  const onlyDisabled: UserSyncRunProgressPayload = {
    phase_progress: {
      reconcile: { current: 1, total: 1, status: 'finish', counters: { disabled_users: 5, deleted_group_count: 0 } },
    },
  };
  assert.equal(formatPhaseCounterLine('reconcile', onlyDisabled, t), '禁用 5');

  // reconcile 都 0 → 空串
  const reconcileZero: UserSyncRunProgressPayload = {
    phase_progress: {
      reconcile: { current: 1, total: 1, status: 'finish', counters: { disabled_users: 0, deleted_group_count: 0 } },
    },
  };
  assert.equal(formatPhaseCounterLine('reconcile', reconcileZero, t), '');

  // sync_groups: 新建 3 个组织
  const groupsPayload: UserSyncRunProgressPayload = {
    phase_progress: {
      sync_groups: { current: 3, total: 3, status: 'finish', counters: { created_groups: 3, updated_groups: 0 } },
    },
  };
  assert.equal(formatPhaseCounterLine('sync_groups', groupsPayload, t), '已新建 3 个组织');

  // fetch_directory: 无 counters
  const fetchPayload: UserSyncRunProgressPayload = {
    phase_progress: {
      fetch_directory: { current: 212, total: 212, status: 'finish' },
    },
  };
  assert.equal(formatPhaseCounterLine('fetch_directory', fetchPayload, t), '');

  // finalize: 不在 counters 里(邮件走 email_status)
  assert.equal(formatPhaseCounterLine('finalize', {} as UserSyncRunProgressPayload, t), '');

  console.log('  ✓ formatPhaseCounterLine');
}

// --- formatPhaseBusinessResult ---

function testFormatPhaseBusinessResult() {
  assert.equal(
    formatPhaseBusinessResult(
      'fetch_directory',
      { input_summary: { fetched_user_count: 12, fetched_group_count: 3 } },
      t,
    ),
    '已获取 12 名用户 · 3 个组织',
  );
  assert.equal(
    formatPhaseBusinessResult(
      'reconcile',
      { phase_progress: { reconcile: { current: 1, total: 1, status: 'finish', counters: { disabled_users: 2, deleted_group_count: 1 } } } },
      t,
    ),
    '已禁用 2 名用户 · 已移除 1 个组织',
  );
  assert.equal(
    formatPhaseBusinessResult(
      'reconcile',
      { phase_progress: { reconcile: { current: 1, total: 1, status: 'finish', counters: { disabled_users: 0, deleted_group_count: 0 } } } },
      t,
    ),
    '未发现需清理的用户或组织',
  );
  assert.equal(
    formatPhaseBusinessResult(
      'sync_groups',
      { phase_progress: { sync_groups: { current: 3, total: 3, status: 'finish', counters: { created_groups: 0, updated_groups: 0 } } } },
      t,
    ),
    '已核验 3 个组织，未发现变更',
  );
  assert.equal(
    formatPhaseBusinessResult(
      'sync_users',
      { phase_progress: { sync_users: { current: 1, total: 1, status: 'finish', counters: { new_users: 0, updated_users: 0, conflict_users: 0 } } } },
      t,
    ),
    '已核验 1 名用户，未发现变更',
  );
  console.log('  ✓ formatPhaseBusinessResult');
}

// --- formatEmailNotificationResult ---

function testFormatEmailNotificationResult() {
  assert.equal(
    formatEmailNotificationResult({ email_status: { total: 2, sent: 0, failed: 0, completed: false } }, t),
    '邮件已入队，待发送 2 封',
  );
  assert.equal(
    formatEmailNotificationResult({ email_status: { total: 2, sent: 1, failed: 0, completed: false } }, t),
    '邮件发送中，已发送 1 / 2 封',
  );
  assert.equal(
    formatEmailNotificationResult({ email_status: { total: 2, sent: 2, failed: 0, completed: true } }, t),
    '邮件已完成，成功 2 封',
  );
  assert.equal(
    formatEmailNotificationResult({ email_status: { total: 2, sent: 1, failed: 1, completed: true } }, t),
    '邮件发送失败 1 封',
  );
  assert.equal(
    formatEmailNotificationResult(
      { phase_progress: { finalize: { current: 0, total: 0, status: 'skipped', skip_reason: 'no_new_users' } } },
      t,
    ),
    '本次未新建用户，无需发送初始密码通知',
  );
  console.log('  ✓ formatEmailNotificationResult');
}

function testFormatPhaseErrorMessage() {
  assert.equal(
    formatUserSyncErrorMessage('provider_fetch_failed', t),
    '目录拉取失败，请检查同步源配置和连接状态',
  );
  assert.equal(
    formatPhaseErrorMessage({ phase_error: { phase: 'fetch_directory', current: 0, total: 0, error_code: 'provider_fetch_failed', failed_at: '' } }, t),
    '目录拉取失败，请检查同步源配置和连接状态',
  );
  assert.equal(
    formatPhaseErrorMessage({ phase_error: { phase: 'sync_users', current: 0, total: 1, error_message: 'legacy message', failed_at: '' } }, t),
    'legacy message',
  );
  console.log('  ✓ formatPhaseErrorMessage');
}

// --- formatPhaseProgressMeta ---

function testFormatPhaseProgressMeta() {
  assert.equal(
    formatPhaseProgressMeta(
      { current: 24, total: 100, status: 'process' },
      '新建 8 · 更新 16',
      t,
    ),
    '已处理 24 / 100 · 新建 8 · 更新 16',
  );

  assert.equal(
    formatPhaseProgressMeta(
      { current: 100, total: 100, status: 'finish' },
      '已同步 3 个组织',
      t,
    ),
    '已同步 3 个组织',
  );

  assert.equal(
    formatPhaseProgressMeta(
      { current: 0, total: 0, status: 'wait' },
      '',
      t,
    ),
    '',
  );
  console.log('  ✓ formatPhaseProgressMeta');
}

// --- getPhaseDisplayProgress ---

function testGetPhaseDisplayProgress() {
  const emailSendingPayload: UserSyncRunProgressPayload = {
    phase_progress: {
      // 1/1 只表示邮件任务已成功入队，不是邮件发送进度。
      finalize: { current: 1, total: 1, status: 'finish' },
    },
    email_status: { total: 42, sent: 18, failed: 0, completed: false },
  };

  assert.equal(
    getPhaseDisplayStatus('finalize', safeGetPhaseProgress(emailSendingPayload, 'finalize'), emailSendingPayload),
    'process',
  );
  assert.deepStrictEqual(
    getPhaseDisplayProgress('finalize', safeGetPhaseProgress(emailSendingPayload, 'finalize'), emailSendingPayload),
    { current: 18, total: 42 },
  );
  assert.deepStrictEqual(
    getPhaseDisplayProgress(
      'sync_users',
      { current: 48, total: 120, status: 'process' },
      emailSendingPayload,
    ),
    { current: 48, total: 120 },
  );
  assert.equal(
    getPhaseDisplayStatus(
      'finalize',
      { current: 1, total: 1, status: 'finish' },
      { email_status: { total: 42, sent: 40, failed: 2, completed: true } },
    ),
    'error',
  );
  console.log('  ✓ getPhaseDisplayProgress');
}

// --- shouldExpandPhase ---

function testShouldExpandPhase() {
  assert.equal(
    shouldExpandPhase({ current: 8, total: 8, status: 'finish' }),
    true,
  );
  assert.equal(
    shouldExpandPhase({ current: 8, total: 10, status: 'process' }),
    true,
  );
  assert.equal(
    shouldExpandPhase({ current: 8, total: 10, status: 'error' }),
    true,
  );
  assert.equal(
    shouldExpandPhase({ current: 1, total: 1, status: 'finish' }),
    true,
  );
  assert.equal(
    shouldExpandPhase({ current: 0, total: 0, status: 'skipped' }),
    true,
  );
  console.log('  ✓ shouldExpandPhase');
}

// --- formatElapsed ---

function testFormatElapsed() {
  // 0 秒
  assert.equal(formatElapsed('2026-07-22T10:00:00Z', '2026-07-22T10:00:00Z', t, () => new Date('2026-07-22T10:00:00Z')), '耗时 00:00');
  // 1 分 30 秒
  assert.equal(
    formatElapsed('2026-07-22T10:00:00Z', '2026-07-22T10:01:30Z', t, () => new Date('2026-07-22T10:01:30Z')),
    '耗时 01:30',
  );
  // 1 小时 1 分 1 秒
  assert.equal(
    formatElapsed('2026-07-22T10:00:00Z', '2026-07-22T11:01:01Z', t, () => new Date('2026-07-22T11:01:01Z')),
    '耗时 01:01:01',
  );
  // finished_at 为 null → 用 now
  assert.equal(
    formatElapsed('2026-07-22T10:00:00Z', null, t, () => new Date('2026-07-22T10:00:42Z')),
    '耗时 00:42',
  );
  // started_at 缺 → 空
  assert.equal(formatElapsed(null, null, t, () => new Date()), '');
  console.log('  ✓ formatElapsed');
}

// --- safeGetPhaseProgress ---

function testSafeGetPhaseProgress() {
  // 空 payload
  assert.deepStrictEqual(
    safeGetPhaseProgress(null, 'sync_users'),
    { current: 0, total: 0, status: 'wait' },
  );
  // payload 没 phase_progress
  assert.deepStrictEqual(
    safeGetPhaseProgress({} as UserSyncRunProgressPayload, 'sync_users'),
    { current: 0, total: 0, status: 'wait' },
  );
  // phase_progress 缺该 phase
  assert.deepStrictEqual(
    safeGetPhaseProgress(
      { phase_progress: { fetch_directory: { current: 1, total: 1, status: 'finish' } } } as UserSyncRunProgressPayload,
      'sync_users',
    ),
    { current: 0, total: 0, status: 'wait' },
  );
  // 完整 entry
  assert.deepStrictEqual(
    safeGetPhaseProgress(
      { phase_progress: { sync_users: { current: 50, total: 200, status: 'process' } } } as UserSyncRunProgressPayload,
      'sync_users',
    ),
    { current: 50, total: 200, status: 'process' },
  );
  // 缺字段时默认为 0 / 'wait'
  assert.deepStrictEqual(
    safeGetPhaseProgress(
      { phase_progress: { sync_users: {} as unknown as { current: number; total: number; status: 'process' } } } as UserSyncRunProgressPayload,
      'sync_users',
    ),
    { current: 0, total: 0, status: 'wait' },
  );
  console.log('  ✓ safeGetPhaseProgress');
}

// --- finalize 与 email_status 解耦 ---

function testFinalizeIndependence() {
  // finalize 阶段独立于 email_status:即使 email 有失败,finalize phase 仍可 finish
  const payload: UserSyncRunProgressPayload = {
    password_init_mode: 'uniform',
    phase_progress: {
      fetch_directory: { current: 12, total: 12, status: 'finish' },
      sync_groups: { current: 2, total: 2, status: 'finish' },
      sync_users: { current: 5, total: 5, status: 'finish' },
      reconcile: { current: 1, total: 1, status: 'finish' },
      finalize: { current: 1, total: 1, status: 'finish' },
    },
    email_status: { total: 5, sent: 3, failed: 2, completed: false },
  };
  // finalize 阶段 status=finish
  assert.equal(safeGetPhaseProgress(payload, 'finalize').status, 'finish');
  // email_status 显示独立失败
  assert.equal(payload.email_status?.failed, 2);
  assert.equal(payload.email_status?.completed, false);
  console.log('  ✓ finalize 与 email_status 解耦');
}

// --- calcPercent ---

function testCalcPercent() {
  assert.equal(calcPercent(0, 0), 0); // 0/0 → 0
  assert.equal(calcPercent(50, 200), 25);
  assert.equal(calcPercent(200, 200), 100);
  assert.equal(calcPercent(250, 200), 100); // 上限
  assert.equal(calcPercent(-5, 100), 0); // 下限
  console.log('  ✓ calcPercent');
}

function main() {
  console.log('userSyncProgress tests:');
  testGetPhasesForRun();
  testGetPhaseStatusConfig();
  testGetPhaseLabel();
  testPhaseLabelsInLocales();
  testDrawerVisualHierarchy();
  testFormatPhaseCounterLine();
  testFormatPhaseBusinessResult();
  testFormatEmailNotificationResult();
  testFormatPhaseErrorMessage();
  testFormatPhaseProgressMeta();
  testGetPhaseDisplayProgress();
  testShouldExpandPhase();
  testFormatElapsed();
  testSafeGetPhaseProgress();
  testFinalizeIndependence();
  testCalcPercent();
  console.log('  all 11 groups passed');
}

main();
