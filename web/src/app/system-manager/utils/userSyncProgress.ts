/**
 * 用户同步进度展示 helper
 *
 * 与 node-manager/utils/installerProgress.ts 对齐:提供阶段枚举、状态映射、
 * 计数器格式化、阶段动态生成等纯函数,供 Drawer 与单测使用。
 */
import type {
  PhaseKey,
  PhaseProgressEntry,
  PhaseStatus,
  UserSyncRunProgressPayload,
} from '@/app/system-manager/types/user-sync';

/** 静态 4 阶段(无论 password_init.mode 都展示)。 */
export const STATIC_PHASES: PhaseKey[] = [
  'fetch_directory',
  'sync_groups',
  'sync_users',
  'reconcile',
];

/** 终态阶段 — 仅 mode=uniform/random 出现。 */
export const FINALIZE_PHASE: PhaseKey = 'finalize';

const EMPTY_PHASE_ENTRY: PhaseProgressEntry = { current: 0, total: 0, status: 'wait' };

/** 根据 run payload 决定展示的阶段列表。mode 不为 none 时追加 finalize。 */
export function getPhasesForRun(payload: UserSyncRunProgressPayload | null | undefined): PhaseKey[] {
  const phases: PhaseKey[] = [...STATIC_PHASES];
  const mode = payload?.password_init_mode;
  if (mode && mode !== 'none') {
    phases.push(FINALIZE_PHASE);
  }
  return phases;
}

/** 安全从 payload 读 phase_progress,缺字段返回 wait 占位。 */
export function safeGetPhaseProgress(
  payload: UserSyncRunProgressPayload | null | undefined,
  phase: PhaseKey,
): PhaseProgressEntry {
  const entry = payload?.phase_progress?.[phase];
  if (!entry) return { ...EMPTY_PHASE_ENTRY };
  const progress: PhaseProgressEntry = {
    current: Number(entry.current ?? 0),
    total: Number(entry.total ?? 0),
    status: (entry.status as PhaseStatus) ?? 'wait',
  };
  if (entry.completed_at) progress.completed_at = entry.completed_at;
  return progress;
}

/** 阶段状态 → antd Tag 颜色 + icon + 文本。 */
export interface PhaseStatusConfig {
  tagColor: string;
  stepStatus: 'wait' | 'process' | 'finish' | 'error';
  text: string;
  icon: 'check' | 'loading' | 'clock' | 'close' | 'minus';
}

// /api/locales 用 flattenMessages 把嵌套 JSON 展平为点号路径,
// 所以 helper 必须用完整路径 `system.user.userSyncPage.<key>`,与既有 keys 对齐
const P = 'system.user.userSyncPage';

const PHASE_ERROR_MESSAGE_KEYS: Record<string, string> = {
  sync_failed: 'syncFailed',
  provider_fetch_failed: 'providerFetchFailed',
  data_conflict: 'dataConflict',
  database_unavailable: 'databaseUnavailable',
  request_timeout: 'requestTimeout',
  external_service_unavailable: 'externalServiceUnavailable',
  invalid_sync_data: 'invalidSyncData',
  email_enqueue_failed: 'emailEnqueueFailed',
};

/** 将后端持久化的语言无关错误码转为当前界面语言。 */
export function formatUserSyncErrorMessage(
  errorCode: string | null | undefined,
  t: (key: string, fallback?: string) => string,
): string {
  const messageKey = errorCode && PHASE_ERROR_MESSAGE_KEYS[errorCode];
  return messageKey ? t(`${P}.phaseError.${messageKey}`) : t(`${P}.phaseError.syncFailed`);
}

export function getPhaseStatusConfig(
  status: PhaseStatus,
  t: (key: string, fallback?: string) => string,
): PhaseStatusConfig {
  switch (status) {
    case 'finish':
      return { tagColor: 'success', stepStatus: 'finish', text: t(`${P}.phaseStatus.finish`), icon: 'check' };
    case 'process':
      return { tagColor: 'processing', stepStatus: 'process', text: t(`${P}.phaseStatus.process`), icon: 'loading' };
    case 'error':
      return { tagColor: 'error', stepStatus: 'error', text: t(`${P}.phaseStatus.error`), icon: 'close' };
    case 'skipped':
      return { tagColor: 'default', stepStatus: 'wait', text: t(`${P}.phaseStatus.skipped`), icon: 'minus' };
    case 'wait':
    default:
      return { tagColor: 'default', stepStatus: 'wait', text: t(`${P}.phaseStatus.wait`), icon: 'clock' };
  }
}

/** 阶段 key → 标题文本(取 i18n,无 defaultMessage 兜底 —— 缺失 key 直接显示 key 路径,显式可见)。 */
export function getPhaseLabel(phase: PhaseKey, t: (key: string, fallback?: string) => string): string {
  const map: Record<PhaseKey, string> = {
    fetch_directory: t(`${P}.phase.fetchDirectory`),
    sync_groups: t(`${P}.phase.syncGroups`),
    sync_users: t(`${P}.phase.syncUsers`),
    reconcile: t(`${P}.phase.reconcile`),
    finalize: t(`${P}.phase.finalize`),
  };
  return map[phase];
}

/** per-phase counter 行(每个阶段只显示本阶段关心的数字)。

- 拉取目录 / 同步组织:无 counters(空)
- 同步用户:新建 / 更新 / 冲突(零值字段不显示)
- 全量对账:禁用 / 删除(零值字段不显示)
- 收尾邮件:已入队(由 caller 单独从 email_status 拼,本 helper 不管)
- 计数全 0 时返回空串,不显示多余行
*/
export function formatPhaseCounterLine(
  phase: PhaseKey,
  payload: UserSyncRunProgressPayload | null | undefined,
  t: (key: string, fallback?: string) => string,
): string {
  const counters = payload?.phase_progress?.[phase]?.counters;
  if (!counters) return '';

  switch (phase) {
    case 'sync_users': {
      // 只显示 > 0 的字段,避免「新建 1 · 更新 0 · 冲突 0」这种零值噪音
      const parts: string[] = [];
      if ((counters.new_users ?? 0) > 0) {
        parts.push(t(`${P}.phaseCounter.syncUsersNew`).replace('{{n}}', String(counters.new_users)));
      }
      if ((counters.updated_users ?? 0) > 0) {
        parts.push(t(`${P}.phaseCounter.syncUsersUpdated`).replace('{{n}}', String(counters.updated_users)));
      }
      if ((counters.conflict_users ?? 0) > 0) {
        parts.push(t(`${P}.phaseCounter.syncUsersConflict`).replace('{{n}}', String(counters.conflict_users)));
      }
      return parts.join(' · ');
    }
    case 'reconcile': {
      const parts: string[] = [];
      if ((counters.disabled_users ?? 0) > 0) {
        parts.push(t(`${P}.phaseCounter.reconcileDisabled`).replace('{{n}}', String(counters.disabled_users)));
      }
      if ((counters.deleted_group_count ?? 0) > 0) {
        parts.push(t(`${P}.phaseCounter.reconcileDeleted`).replace('{{n}}', String(counters.deleted_group_count)));
      }
      return parts.join(' · ');
    }
    case 'sync_groups': {
      const parts: string[] = [];
      if ((counters.created_groups ?? 0) > 0) {
        parts.push(t(`${P}.phaseCounter.syncGroupsCreated`).replace('{{n}}', String(counters.created_groups)));
      }
      if ((counters.updated_groups ?? 0) > 0) {
        parts.push(t(`${P}.phaseCounter.syncGroupsUpdated`).replace('{{n}}', String(counters.updated_groups)));
      }
      return parts.join(' · ');
    }
    case 'finalize': {
      // finalize 阶段 counter 由 email_status 决定,这里返回空
      return '';
    }
    case 'fetch_directory':
    default:
      return '';
  }
}

/** 阶段业务结果：避免向用户暴露内部步骤计数或英文任务摘要。 */
export function formatPhaseBusinessResult(
  phase: PhaseKey,
  payload: UserSyncRunProgressPayload | null | undefined,
  t: (key: string, fallback?: string) => string,
): string {
  if (phase === 'fetch_directory') {
    const input = payload?.input_summary;
    return t(`${P}.phaseResult.fetchDirectory`)
      .replace('{{users}}', String(input?.fetched_user_count ?? 0))
      .replace('{{groups}}', String(input?.fetched_group_count ?? 0));
  }
  if (phase === 'reconcile') {
    const counters = payload?.phase_progress?.reconcile?.counters;
    const disabledUsers = Number(counters?.disabled_users ?? 0);
    const deletedGroups = Number(counters?.deleted_group_count ?? 0);
    if (disabledUsers === 0 && deletedGroups === 0) {
      return t(`${P}.phaseResult.reconcileUnchanged`);
    }
    return t(`${P}.phaseResult.reconcileChanged`)
      .replace('{{users}}', String(disabledUsers))
      .replace('{{groups}}', String(deletedGroups));
  }
  if (phase === 'sync_groups') {
    const entry = payload?.phase_progress?.sync_groups;
    const counters = entry?.counters;
    const createdGroups = Number(counters?.created_groups ?? 0);
    const updatedGroups = Number(counters?.updated_groups ?? 0);
    if (createdGroups === 0 && updatedGroups === 0) {
      return t(`${P}.phaseResult.syncGroupsUnchanged`)
        .replace('{{groups}}', String(entry?.total ?? entry?.current ?? 0));
    }
    return formatPhaseCounterLine(phase, payload, t);
  }
  if (phase === 'sync_users') {
    const entry = payload?.phase_progress?.sync_users;
    const counters = entry?.counters;
    const hasChanges = (counters?.new_users ?? 0) > 0
      || (counters?.updated_users ?? 0) > 0
      || (counters?.conflict_users ?? 0) > 0;
    if (!hasChanges && entry?.status === 'finish') {
      return t(`${P}.phaseResult.syncUsersUnchanged`)
        .replace('{{users}}', String(entry.total ?? entry.current ?? 0));
    }
  }
  return formatPhaseCounterLine(phase, payload, t);
}

/** 初始密码通知的异步投递状态。 */
export function formatEmailNotificationResult(
  payload: UserSyncRunProgressPayload | null | undefined,
  t: (key: string, fallback?: string) => string,
): string {
  const finalize = payload?.phase_progress?.finalize;
  if (finalize?.status === 'skipped') {
    if (finalize.skip_reason === 'no_new_users') {
      return t(`${P}.phaseResult.emailSkippedNoNewUsers`);
    }
    return t(`${P}.phaseResult.emailSkipped`);
  }
  const emailStatus = payload?.email_status;
  if (!emailStatus) return '';
  const total = Number(emailStatus.total ?? 0);
  const sent = Number(emailStatus.sent ?? 0);
  const failed = Number(emailStatus.failed ?? 0);
  if (failed > 0) {
    return t(`${P}.phaseResult.emailFailed`).replace('{{failed}}', String(failed));
  }
  if (emailStatus.completed) {
    return t(`${P}.phaseResult.emailCompleted`).replace('{{sent}}', String(sent));
  }
  if (sent > 0) {
    return t(`${P}.phaseResult.emailSending`)
      .replace('{{sent}}', String(sent))
      .replace('{{total}}', String(total));
  }
  return t(`${P}.phaseResult.emailQueued`).replace('{{total}}', String(total));
}

/** 阶段错误按当前界面语言渲染；旧记录保留 error_message 作为回退。 */
export function formatPhaseErrorMessage(
  payload: UserSyncRunProgressPayload | null | undefined,
  t: (key: string, fallback?: string) => string,
): string {
  const phaseError = payload?.phase_error;
  if (!phaseError) return '';
  if (phaseError.error_code) return formatUserSyncErrorMessage(phaseError.error_code, t);
  return phaseError.error_message || t(`${P}.phaseError.syncFailed`);
}

/**
 * finalize=finish 仅表示 broker 已接收任务；邮件投递尚未结束时，
 * Drawer 仍需把该步骤视为进行中，并在全部失败/成功后给出最终状态。
 */
export function getPhaseDisplayStatus(
  phase: PhaseKey,
  entry: PhaseProgressEntry,
  payload: UserSyncRunProgressPayload | null | undefined,
): PhaseStatus {
  if (phase !== 'finalize' || entry.status !== 'finish') return entry.status;

  const emailStatus = payload?.email_status;
  if (!emailStatus) return entry.status;
  if (!emailStatus.completed) return 'process';
  return Number(emailStatus.failed ?? 0) > 0 ? 'error' : entry.status;
}

/**
 * 进度条采用的计数。邮件阶段的 1/1 仅代表任务已入队，
 * 发送过程中应改用 email_status，避免显示“进行中”却是满格进度。
 */
export function getPhaseDisplayProgress(
  phase: PhaseKey,
  entry: PhaseProgressEntry,
  payload: UserSyncRunProgressPayload | null | undefined,
): Pick<PhaseProgressEntry, 'current' | 'total'> {
  if (phase === 'finalize' && !payload?.email_status?.completed) {
    const emailStatus = payload?.email_status;
    const total = Number(emailStatus?.total ?? 0);
    if (total > 0) {
      return { current: Number(emailStatus?.sent ?? 0), total };
    }
  }
  return { current: entry.current, total: entry.total };
}

/** 阶段的简要进度信息：仅在进行中展示连续进度，避免重复任务级时间戳。 */
export function formatPhaseProgressMeta(
  entry: PhaseProgressEntry,
  counterLine: string,
  t: (key: string, fallback?: string) => string,
): string {
  const parts: string[] = [];
  if (entry.status === 'process' && entry.total > 0) {
    parts.push(
      t(`${P}.progressDrawer.processed`)
        .replace('{{current}}', String(entry.current))
        .replace('{{total}}', String(entry.total)),
    );
  }
  if (counterLine) parts.push(counterLine);
  return parts.join(' · ');
}

/** 只有需要持续反馈或承载细节的阶段才展开 description 区域。 */
export function shouldExpandPhase(entry: PhaseProgressEntry): boolean {
  return entry.status !== 'wait';
}

/** 耗时 mm:ss 或 hh:mm:ss。finished_at 为 null 时按当前时间算。

- t 默认无 fallback:缺失 key 直接显示 key 路径,便于发现
- now 默认 Date.now,测试可注入固定时间
*/
export function formatElapsed(
  startedAt: string | null | undefined,
  finishedAt: string | null | undefined,
  t: (key: string, fallback?: string) => string,
  now: () => Date = () => new Date(),
): string {
  if (!startedAt) return '';
  const start = new Date(startedAt);
  const end = finishedAt ? new Date(finishedAt) : now();
  const seconds = Math.max(0, Math.floor((end.getTime() - start.getTime()) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  const formatted = hours > 0 ? `${pad(hours)}:${pad(minutes)}:${pad(secs)}` : `${pad(minutes)}:${pad(secs)}`;
  return t(`${P}.progressDrawer.elapsed`).replace('{{duration}}', formatted);
}

/** 进度条 percent(0-100)。total=0 时返回 0(避免除零)。 */
export function calcPercent(current: number, total: number): number {
  if (!total || total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
}
