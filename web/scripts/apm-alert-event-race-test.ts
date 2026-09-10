import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createLatestRequestGuard } from '../src/context/latestRequestGuard.ts';
import type { LatestRequestGuard } from '../src/context/latestRequestGuard.ts';
import type { ApmAlertEvent, ApmEventSnapshot, ApmNotificationDelivery } from '../src/app/apm/types.ts';

interface AlertEventRequestKey {
  alertId: string;
  eventId: string;
}

interface AlertEventCommitFns {
  commitAlertEventEvidenceSuccess: (
    guard: LatestRequestGuard,
    requestId: number,
    requested: AlertEventRequestKey,
    snapshots: ApmEventSnapshot[],
    deliveries: ApmNotificationDelivery[],
    apply: (evidence: ApmEventSnapshot | null, deliveries: ApmNotificationDelivery[]) => void,
  ) => boolean;
  commitAlertEventEvidenceSettled: (
    guard: LatestRequestGuard,
    requestId: number,
    settle: () => void,
  ) => boolean;
  canRetryAlertEventDelivery: (
    delivery: ApmNotificationDelivery | undefined,
    selectedEvent: Pick<ApmAlertEvent, 'event_id'> | null,
  ) => boolean;
}

interface EventViewState {
  selectedEventId: string | null;
  evidence: ApmEventSnapshot | null;
  deliveries: ApmNotificationDelivery[];
  loading: boolean;
}

const here = dirname(fileURLToPath(import.meta.url));
const pagePath = resolve(here, '../src/app/apm/events/alerts/page.tsx');
const utilPath = resolve(here, '../src/app/apm/utils/alertEventRequest.ts');

function snapshot(eventId: string): ApmEventSnapshot {
  return {
    id: `snap-${eventId}`,
    event_id: eventId,
    schema_version: 1,
    action: 'triggered',
    occurred_at: '2026-09-09T00:00:00Z',
    policy_snapshot: {},
    object_snapshot: {},
    evaluation_snapshot: { value: '1', data_state: 'available' },
    trace_context: { trace_id: `trace-${eventId}` },
    payload_status: 'available',
    payload_error_code: '',
    payload: null,
    retention_expires_at: '2026-09-16T00:00:00Z',
  };
}

function delivery(id: string, eventId: string): ApmNotificationDelivery {
  return {
    id,
    event_id: eventId,
    channel_id: 1,
    channel_name: `channel-${eventId}`,
    channel_type: 'slack',
    delivery_mode: 'message',
    recipients: ['sre'],
    status: 'failed',
    attempts: 1,
    next_retry_at: null,
    last_error_code: 'provider_unavailable',
    last_error_message: 'down',
    delivered_at: null,
    failed_at: '2026-09-09T00:00:00Z',
  };
}

async function loadCommitFns(): Promise<AlertEventCommitFns> {
  let loaded: Partial<AlertEventCommitFns> = {};
  try {
    loaded = await import('../src/app/apm/utils/alertEventRequest.ts');
  } catch {
    // RED：提交函数尚未抽出。
  }

  assert.equal(typeof loaded.commitAlertEventEvidenceSuccess, 'function', '应抽出 commitAlertEventEvidenceSuccess');
  assert.equal(typeof loaded.commitAlertEventEvidenceSettled, 'function', '应抽出 commitAlertEventEvidenceSettled');
  assert.equal(typeof loaded.canRetryAlertEventDelivery, 'function', '应抽出 canRetryAlertEventDelivery');

  return loaded as AlertEventCommitFns;
}

function createEventSession(fns: AlertEventCommitFns) {
  const guard = createLatestRequestGuard();
  let state: EventViewState = {
    selectedEventId: null,
    evidence: null,
    deliveries: [],
    loading: false,
  };

  const choose = (alertId: string, eventId: string) => {
    const requestId = guard.begin();
    state = {
      selectedEventId: eventId,
      evidence: null,
      deliveries: [],
      loading: true,
    };
    return { requestId, alertId, eventId };
  };

  const succeed = (req: AlertEventRequestKey & { requestId: number }, evidence: ApmEventSnapshot, items: ApmNotificationDelivery[]) => {
    fns.commitAlertEventEvidenceSuccess(
      guard,
      req.requestId,
      { alertId: req.alertId, eventId: req.eventId },
      [evidence],
      items,
      (nextEvidence, nextDeliveries) => {
        state = {
          ...state,
          evidence: nextEvidence,
          deliveries: nextDeliveries,
        };
      },
    );
    fns.commitAlertEventEvidenceSettled(guard, req.requestId, () => {
      state = { ...state, loading: false };
    });
  };

  const fail = (req: { requestId: number }) => {
    fns.commitAlertEventEvidenceSettled(guard, req.requestId, () => {
      state = { ...state, loading: false };
    });
  };

  const close = () => {
    guard.invalidate();
    state = {
      selectedEventId: null,
      evidence: null,
      deliveries: [],
      loading: false,
    };
  };

  return {
    getState: () => state,
    choose,
    succeed,
    fail,
    close,
  };
}

function assertPageUsesGeneration(source: string) {
  assert.match(
    source,
    /from ['"]@\/context\/latestRequestGuard['"]/,
    'page 必须复用 @/context/latestRequestGuard，不得复制新 guard',
  );
  assert.match(source, /createLatestRequestGuard/, 'page 必须创建 latest request guard');
  assert.match(source, /\.begin\(\)/, 'chooseEvent 必须按单调序号 begin');
  assert.match(
    source,
    /from ['"]@\/app\/apm\/utils\/alertEventRequest['"]/,
    'page 必须调用抽出的 alertEventRequest',
  );
  assert.match(source, /commitAlertEventEvidenceSuccess\(/, 'chooseEvent 成功必须经序号提交证据和投递');
  assert.match(source, /commitAlertEventEvidenceSettled\(/, 'chooseEvent 结束 loading 必须经序号提交');
  assert.match(source, /\.invalidate\(\)/, '关闭抽屉、换事件或重开告警必须 invalidate');
  assert.match(source, /canRetryAlertEventDelivery\(/, '重投前必须校验 delivery.event_id');
  assert.match(source, /snapshotLoadSequence/, '指标快照序号逻辑必须保持');
  assert.match(
    source,
    /snapshotSequence !== snapshotLoadSequence\.current/,
    '指标快照仍按原序号提交',
  );
  assert.doesNotMatch(
    source,
    /setEventEvidence\(snapshots\[0\]/,
    'chooseEvent 不得在 Promise.then 无条件写 evidence',
  );
  assert.doesNotMatch(
    source,
    /\.finally\(\(\) => setEventEvidenceLoading\(false\)\)/,
    'chooseEvent 不得在 finally 无条件清 loading',
  );
  assert.doesNotMatch(
    source,
    /function createLatestRequestGuard|const createLatestRequestGuard\s*=/,
    '不得在 page 内复制一套序号 guard',
  );
}

async function main() {
  const fns = await loadCommitFns();

  const race = createEventSession(fns);
  const requestA = race.choose('alert-1', 'evt-A');
  const requestB = race.choose('alert-1', 'evt-B');
  race.succeed(requestB, snapshot('evt-B'), [delivery('d-B', 'evt-B')]);
  race.succeed(requestA, snapshot('evt-A'), [delivery('d-A', 'evt-A')]);
  assert.equal(race.getState().selectedEventId, 'evt-B', 'A→B 选择后高亮必须停在 B');
  assert.equal(race.getState().evidence?.event_id, 'evt-B', 'B→A 完成时证据不得回写成 A');
  assert.deepEqual(
    race.getState().deliveries.map((item) => item.id),
    ['d-B'],
    'B→A 完成时投递列表不得回写成 A',
  );
  assert.equal(race.getState().loading, false);

  const closed = createEventSession(fns);
  const lateAfterClose = closed.choose('alert-1', 'evt-A');
  closed.close();
  closed.succeed(lateAfterClose, snapshot('evt-A'), [delivery('d-late', 'evt-A')]);
  assert.equal(closed.getState().selectedEventId, null, '关闭抽屉后所选事件必须清空');
  assert.equal(closed.getState().evidence, null, '关闭抽屉后迟到证据不得写回');
  assert.deepEqual(closed.getState().deliveries, [], '关闭抽屉后迟到投递不得写回');

  const inflight = createEventSession(fns);
  const staleFail = inflight.choose('alert-1', 'evt-A');
  inflight.choose('alert-1', 'evt-B');
  inflight.fail(staleFail);
  assert.equal(inflight.getState().selectedEventId, 'evt-B', '换事件后高亮必须是最新事件');
  assert.equal(inflight.getState().loading, true, '旧失败不得把仍在途的最新请求 loading 清掉');
  assert.equal(inflight.getState().evidence, null, '旧失败不得写回证据');

  const selectedB: Pick<ApmAlertEvent, 'event_id'> = { event_id: 'evt-B' };
  assert.equal(
    fns.canRetryAlertEventDelivery(delivery('d-B', 'evt-B'), selectedB),
    true,
    '当前事件的失败投递必须允许重投',
  );
  assert.equal(
    fns.canRetryAlertEventDelivery(delivery('d-A', 'evt-A'), selectedB),
    false,
    'event_id 与所选事件不一致时必须拒绝重投',
  );
  assert.equal(
    fns.canRetryAlertEventDelivery(delivery('d-null', ''), selectedB),
    false,
    '缺少 event_id 的投递不得重投',
  );
  assert.equal(
    fns.canRetryAlertEventDelivery(undefined, selectedB),
    false,
    '当前列表找不到的投递不得重投',
  );
  assert.equal(
    fns.canRetryAlertEventDelivery(delivery('d-B', 'evt-B'), null),
    false,
    '未选中事件时不得重投',
  );

  const pageSource = readFileSync(pagePath, 'utf8');
  const utilSource = readFileSync(utilPath, 'utf8');
  assertPageUsesGeneration(pageSource);
  assert.doesNotMatch(
    utilSource,
    /createLatestRequestGuard\s*=|function createLatestRequestGuard/,
    'alertEventRequest 不得复制一套序号 guard',
  );
  assert.match(
    utilSource,
    /alertId|eventId/,
    '提交函数必须绑定 alert.id + event.event_id',
  );

  console.log('apm alert event race test passed');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
