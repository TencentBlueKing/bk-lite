import {
  BaseTransport,
  LogLevel,
  type Patterns,
  type TransportItem,
  TransportItemType,
} from '@grafana/faro-web-sdk';
import { classifyItems, createCollectBatch } from './batches';
import { BoundedConcurrentQueue } from './queue';
import {
  buildReplaySegments,
  FARO_REPLAY_PAUSED_EVENT,
  FARO_REPLAY_RESUMED_EVENT,
  FARO_REPLAY_STARTED_EVENT,
  isReplayEvent,
  type ReplaySegment,
} from './replay';
import { type RetryOptions, requestWithRetry } from './retry';

export interface CoreRumTransportOptions {
  apiKey: string;
  collectUrl: string;
  debug?: (event: CoreRumDebugEvent) => void;
  replay?: {
    enabled?: boolean;
    targetSegmentBytes?: number;
    maxSegmentEvents?: number;
  };
  replayUrl: string;
}

export interface CoreRumDebugEvent {
  channel: 'ordinary' | 'replay' | 'traces';
  reason:
    | 'event-too-large'
    | 'invalid-item'
    | 'pagehide-keepalive-unavailable'
    | 'queue-drop'
    | 'request-failed'
    | 'segment-too-large'
    | 'snapshot-required';
}

interface RecordingState {
  accumulator: ReplayAccumulator;
  application: string;
  failed: boolean;
  nextSequence: number;
  queue: BoundedConcurrentQueue;
  recordingId: string;
  sessionId: string;
  userIdentity: string;
}

interface ReplayAccumulator {
  bytes: number;
  firstTimestamp?: number;
  items: TransportItem[];
  timer?: ReturnType<typeof setTimeout>;
}

interface ReplayScope {
  application: string;
  sessionId: string;
  userIdentity: string;
}

interface PendingReplayBoundary extends ReplayScope {
  bytes: number;
  items: TransportItem[];
}

interface ScopedReplayMeta extends ReplayScope {
  item: TransportItem;
}

const MAX_KEEPALIVE_BYTES = 60_000;
const MAX_KEEPALIVE_REQUESTS = 9;
const MAX_REPLAY_META_BYTES = 16 * 1024;
const MAX_COLLECT_BODY_BYTES = 1_000_000;
const MEBIBYTE = 1024 * 1024;
const ORDINARY_QUEUE_MAX_BYTES = 2 * MEBIBYTE;
const ORDINARY_QUEUE_MAX_ITEMS = 1_000;
const REPLAY_QUEUE_MAX_BYTES = 8 * MEBIBYTE;
const REPLAY_BOUNDARY_MAX_BYTES = 4 * MEBIBYTE + MAX_REPLAY_META_BYTES;
const REPLAY_TARGET_BYTES = 256 * 1024;
const REPLAY_TARGET_DURATION_MS = 5_000;
const REPLAY_MAX_SEGMENT_EVENTS = 1_000;
const TRANSPORT_VERSION = '0.1.0';
const APPLICATION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$/;
const PROTOCOL_HEADERS = {
  apiKey: 'X-API-Key',
  application: 'X-RUM-Application',
  batchId: 'X-RUM-Batch-Id',
  sessionId: 'X-Faro-Session-Id',
} as const;

let pendingKeepaliveBytes = 0;
let pendingKeepaliveRequests = 0;
const replayLifecycleFlushers = new Set<() => void>();
let replayLifecycleListenersInstalled = false;

function installReplayLifecycleListeners(): void {
  if (replayLifecycleListenersInstalled || typeof window === 'undefined')
    return;
  replayLifecycleListenersInstalled = true;
  const flushAll = () => {
    // Faro's BatchExecutor also flushes on visibilitychange. The transport
    // may have registered first, so defer until every listener on the current
    // event has run and the final Faro batch has entered our Replay buffer.
    queueMicrotask(() => {
      for (const flush of [...replayLifecycleFlushers]) flush();
    });
  };
  window.addEventListener('pagehide', flushAll);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushAll();
  });
}

function defaultRandomId(): string {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  if (!globalThis.crypto?.getRandomValues) {
    throw new Error('Web Crypto is required by bklite-rum-sdk');
  }
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join(
    '',
  );
}

function byteLength(body: BodyInit): number {
  if (typeof body === 'string')
    return new TextEncoder().encode(body).byteLength;
  if (body instanceof Blob) return body.size;
  if (body instanceof ArrayBuffer) return body.byteLength;
  if (ArrayBuffer.isView(body)) return body.byteLength;
  return MAX_KEEPALIVE_BYTES + 1;
}

function isDroppableOrdinaryItem(item: TransportItem): boolean {
  if (item.type === TransportItemType.EXCEPTION) return false;
  if (item.type === TransportItemType.LOG) {
    const level = (item.payload as { level?: string }).level;
    return level !== LogLevel.ERROR;
  }
  return true;
}

function replayScope(item: TransportItem): ReplayScope | undefined {
  const sessionId = item.meta.session?.id?.trim();
  const application = item.meta.app?.name?.trim();
  if (!sessionId || !application) return undefined;
  return { application, sessionId, userIdentity: replayUserIdentity(item) };
}

// 同一 rrweb 事件的 attributes.event 会被 type/bytes/timestamp 反复读取；入队时一次性
// parse+encode 后挂到 item 引用上，structuredClone 产生的新引用在 clone 处显式继承，
// 避免主线程对同一字符串重复 JSON.parse + TextEncoder().encode。
interface ReplayItemInfo {
  bytes: number;
  timestamp?: number;
  type?: number;
}

const replayItemInfoCache = new WeakMap<TransportItem, ReplayItemInfo>();

function replayItemInfo(item: TransportItem): ReplayItemInfo {
  const cached = replayItemInfoCache.get(item);
  if (cached) return cached;
  const info: ReplayItemInfo = { bytes: 0 };
  const serialized =
    (item.payload as { attributes?: { event?: string } }).attributes?.event ??
    '';
  info.bytes = new TextEncoder().encode(serialized).byteLength;
  if (serialized) {
    try {
      const parsed = JSON.parse(serialized);
      if (Number.isInteger(parsed.type)) info.type = parsed.type;
      if (
        typeof parsed.timestamp === 'number' &&
        Number.isFinite(parsed.timestamp)
      ) {
        info.timestamp = parsed.timestamp;
      }
    } catch {
      // 非法 JSON：type/timestamp 保持 undefined，bytes 仍为实际长度。
    }
  }
  replayItemInfoCache.set(item, info);
  return info;
}

function withReplayItemInfo(
  item: TransportItem,
  info: ReplayItemInfo,
): TransportItem {
  replayItemInfoCache.set(item, info);
  return item;
}

function replayUserIdentity(item: TransportItem): string {
  const userId = item.meta.user?.id?.trim();
  return userId ? `user:${userId}` : 'anonymous';
}

function replayEventType(item: TransportItem): number | undefined {
  return replayItemInfo(item).type;
}

function replayItemBytes(item: TransportItem): number {
  return replayItemInfo(item).bytes;
}

function replayEventTimestamp(item: TransportItem): number | undefined {
  return replayItemInfo(item).timestamp;
}

function scopesMatch(
  left: ReplayScope | undefined,
  right: ReplayScope | undefined,
): boolean {
  return (
    left !== undefined &&
    right !== undefined &&
    left.application === right.application &&
    left.sessionId === right.sessionId &&
    left.userIdentity === right.userIdentity
  );
}

function sameSessionAndApplication(
  left: ReplayScope | undefined,
  right: ReplayScope | undefined,
): boolean {
  return (
    left !== undefined &&
    right !== undefined &&
    left.application === right.application &&
    left.sessionId === right.sessionId
  );
}

function eventName(item: TransportItem): string | undefined {
  if (item.type !== TransportItemType.EVENT) return undefined;
  return (item.payload as { name?: string }).name;
}

function cloneReplayMetaForSnapshot(
  metaItem: TransportItem,
  snapshotItem: TransportItem,
): TransportItem {
  const clone = structuredClone(metaItem);
  const snapshotPayload = snapshotItem.payload as { timestamp?: string };
  const payload = clone.payload as {
    attributes?: { event?: string };
    timestamp?: string;
  };
  const serialized = payload.attributes?.event;
  if (!serialized) return clone;
  const event = JSON.parse(serialized) as { timestamp?: number };
  const snapshotSerialized = (
    snapshotItem.payload as { attributes?: { event?: string } }
  ).attributes?.event;
  if (snapshotSerialized) {
    const snapshotEvent = JSON.parse(snapshotSerialized) as {
      timestamp?: number;
    };
    event.timestamp = snapshotEvent.timestamp;
  }
  clone.meta = structuredClone(snapshotItem.meta);
  payload.timestamp = snapshotPayload.timestamp;
  payload.attributes = { ...payload.attributes, event: JSON.stringify(event) };
  return clone;
}

function reserveKeepalive(bytes: number): {
  keepalive: boolean;
  release: () => void;
} {
  if (
    bytes > MAX_KEEPALIVE_BYTES ||
    pendingKeepaliveBytes + bytes > MAX_KEEPALIVE_BYTES ||
    pendingKeepaliveRequests >= MAX_KEEPALIVE_REQUESTS
  ) {
    return { keepalive: false, release: () => {} };
  }

  pendingKeepaliveBytes += bytes;
  pendingKeepaliveRequests += 1;
  let released = false;
  return {
    keepalive: true,
    release: () => {
      if (released) return;
      released = true;
      pendingKeepaliveBytes = Math.max(0, pendingKeepaliveBytes - bytes);
      pendingKeepaliveRequests = Math.max(0, pendingKeepaliveRequests - 1);
    },
  };
}

function requireApplication(items: TransportItem[]): string {
  const applications = new Set(
    items.map((item) => {
      const application = item.meta.app?.name?.trim() ?? '';
      if (!APPLICATION_PATTERN.test(application)) {
        throw new TypeError(
          'Faro app.name must be a 1-80 character application identifier',
        );
      }
      return application;
    }),
  );
  if (applications.size !== 1) {
    throw new TypeError('one transport request cannot mix applications');
  }
  return applications.values().next().value!;
}

// Replay 边界状态机（隐式，由 pendingReplayBoundary / restartExpected /
// lastActivatedReplay / lastReplayMeta 四个字段 + 事件名联合表达）。
// 改 Faro 生命周期语义或支持多 recording 前，先对照此图确认每个事件把状态推向哪。
//
//   [idle]  无活跃 recording
//     │  enqueueReplay 收到 Meta(type4)+FullSnapshot(type2)，scope 校验通过
//     ▼
//   [active recording]  recordings 恰有一条 state，accumulator 累积增量事件
//     │  达到 targetBytes/targetDuration/maxEvents，或 pagehide/visibilitychange
//     ▼  flushReplayAccumulator → buildReplaySegments → sendReplaySegment
//   [active recording]  （冲刷后回到 active，序列号 nextSequence 单调递增）
//     │
//     │  以下任一发生，走 quarantineRecording 整体废弃（绝不丢单个段）：
//     │   · 缺 FullSnapshot（snapshot-required）· 事件类型非法（invalid-item）
//     │   · 队列满且段不可丢（queue-drop）      · 发送失败（request-failed）
//     ▼
//   [failed]  state.failed=true，清空 accumulator；只能由失败之后新到的
//     │        Meta+FullSnapshot 重新激活（复用失败前的 Meta 会伪造检查点）
//     ▼
//   [active recording]  activateRecording 重建（新 recordingId，nextSequence 归零）
//
//  scope（application+sessionId+userIdentity）变化永不续写旧 recording：
//  enqueueReplay 先冲刷并清空 recordings，要求新 scope 自带 Meta+FullSnapshot 引导。
export class CoreRumTransport extends BaseTransport {
  readonly name = 'bklite-rum-sdk';
  readonly version = TRANSPORT_VERSION;

  private readonly ordinaryQueue: BoundedConcurrentQueue;
  private readonly replayQueue: BoundedConcurrentQueue;
  private readonly recordings = new Map<string, RecordingState>();
  private readonly randomId: () => string;
  private readonly retryOptions: RetryOptions;
  private lastReplayMeta?: ScopedReplayMeta;
  private lastActivatedReplay?: ReplayScope;
  private pendingReplayBoundary?: PendingReplayBoundary;
  private replayTimerFlush?: Promise<void>;
  private restartExpected?: ReplayScope;
  private readonly flushOnPageLifecycle = () => {
    void this.settle('replay', this.flushActiveReplay(true));
  };

  constructor(private readonly options: CoreRumTransportOptions) {
    super();
    if (!options.apiKey.trim()) throw new TypeError('apiKey is required');
    if (!options.collectUrl.trim())
      throw new TypeError('collectUrl is required');
    if (!options.replayUrl.trim()) throw new TypeError('replayUrl is required');

    // Tests inject deterministic browser primitives through an intentionally
    // unexported structural extension. The published SDK contract has fixed
    // retry policy and exposes no transport-protocol tuning.
    const testRuntime = options as CoreRumTransportOptions &
      RetryOptions & { randomId?: () => string };
    this.randomId = testRuntime.randomId ?? defaultRandomId;
    this.retryOptions = {
      fetch: testRuntime.fetch,
      sleep: testRuntime.sleep,
      random: testRuntime.random,
      maxRetries: testRuntime.maxRetries,
      baseDelayMs: testRuntime.baseDelayMs,
      maxDelayMs: testRuntime.maxDelayMs,
    };
    installReplayLifecycleListeners();
    this.ordinaryQueue = new BoundedConcurrentQueue(
      {
        maxInFlight: 2,
        maxQueuedBytes: ORDINARY_QUEUE_MAX_BYTES,
        maxQueuedItems: ORDINARY_QUEUE_MAX_ITEMS,
      },
      () => this.debug('ordinary', 'queue-drop'),
    );
    this.replayQueue = this.createReplayQueue();
  }

  override getIgnoreUrls(): Patterns {
    return [this.options.collectUrl, this.options.replayUrl];
  }

  override isBatched(): boolean {
    return true;
  }

  async send(input: TransportItem | TransportItem[]): Promise<void> {
    const items = Array.isArray(input) ? input : [input];
    if (items.length === 0) return;
    try {
      requireApplication(items);
    } catch {
      this.debug('ordinary', 'invalid-item');
      return;
    }

    const { collect, replay, traces } = classifyItems(items);
    const operations: Promise<void>[] = [];
    if (collect.length > 0) {
      const channel = traces.length === collect.length ? 'traces' : 'ordinary';
      operations.push(
        this.settle(
          channel,
          this.enqueueCollect(collect, this.ordinaryQueue, channel),
        ),
      );
    }
    if (this.options.replay?.enabled === true) {
      operations.push(
        ...this.prepareReplayOperations(replay).map((operation) =>
          this.settle('replay', operation),
        ),
      );
    }

    await Promise.all(operations);
  }

  async flushReplay(): Promise<void> {
    await Promise.all([
      this.replayTimerFlush ?? Promise.resolve(),
      this.settle('replay', this.flushActiveReplay()),
    ]);
  }

  private prepareReplayOperations(items: TransportItem[]): Promise<void>[] {
    const operations: Promise<void>[] = [];
    let replay: TransportItem[] = [];

    const flush = (
      lifecycle: { boundary?: ReplayScope; boundaryName?: string } = {},
    ) => {
      const operation = this.prepareReplayOperation(replay, lifecycle);
      if (operation) operations.push(operation);
      replay = [];
    };

    for (const item of items) {
      if (isReplayEvent(item)) {
        const currentScope = replay[0] ? replayScope(replay[0]) : undefined;
        const nextScope = replayScope(item);
        if (replay.length > 0 && !scopesMatch(currentScope, nextScope)) flush();
        replay.push(item);
        continue;
      }

      const name = eventName(item);
      if (name === FARO_REPLAY_PAUSED_EVENT) {
        // Preserve Faro's original ordering: anything before pause closes the
        // old recording; only following replay items belong to the pending
        // resume bootstrap.
        flush();
        const operation = this.flushActiveReplay();
        operations.push(operation);
        this.observeReplayLifecycle([item]);
      } else if (
        name === FARO_REPLAY_STARTED_EVENT ||
        name === FARO_REPLAY_RESUMED_EVENT
      ) {
        const lifecycle = this.observeReplayLifecycle([item]);
        flush(lifecycle);
      } else {
        this.debug('replay', 'invalid-item');
      }
    }

    flush();
    return operations;
  }

  private observeReplayLifecycle(items: TransportItem[]): {
    boundary?: ReplayScope;
    boundaryName?: string;
  } {
    let boundary: ReplayScope | undefined;
    let boundaryName: string | undefined;

    for (const item of items) {
      const name = eventName(item);
      if (
        name !== FARO_REPLAY_PAUSED_EVENT &&
        name !== FARO_REPLAY_STARTED_EVENT &&
        name !== FARO_REPLAY_RESUMED_EVENT
      ) {
        continue;
      }
      const scope = replayScope(item);
      if (!scope) continue;
      if (name === FARO_REPLAY_PAUSED_EVENT) {
        this.restartExpected = scope;
        // A new pause supersedes any incomplete prior boundary. Carrying its
        // staged events across another lifecycle edge could join two
        // recordings under one snapshot root.
        this.pendingReplayBoundary = undefined;
        continue;
      }
      boundary = scope;
      boundaryName = name;
    }

    return { boundary, boundaryName };
  }

  private prepareReplayOperation(
    replay: TransportItem[],
    lifecycle: { boundary?: ReplayScope; boundaryName?: string },
  ): Promise<void> | undefined {
    const incomingScope = replay[0] ? replayScope(replay[0]) : undefined;
    if (
      incomingScope &&
      sameSessionAndApplication(this.restartExpected, incomingScope) &&
      !scopesMatch(this.restartExpected, incomingScope)
    ) {
      // Identity can change while recording is paused. Bind the pending
      // boundary to the identity carried by the new rrweb bootstrap so the
      // subsequent resumed event cannot retire the freshly-started stream.
      this.restartExpected = incomingScope;
    }
    const pendingMatches = scopesMatch(
      this.pendingReplayBoundary,
      incomingScope,
    );
    const restartMatches = scopesMatch(this.restartExpected, incomingScope);
    const boundaryMatches = scopesMatch(lifecycle.boundary, incomingScope);
    const isResume = lifecycle.boundaryName === FARO_REPLAY_RESUMED_EVENT;
    const forceBoundary =
      lifecycle.boundary !== undefined &&
      (isResume || lifecycle.boundaryName === FARO_REPLAY_STARTED_EVENT) &&
      (boundaryMatches ||
        scopesMatch(this.pendingReplayBoundary, lifecycle.boundary) ||
        scopesMatch(this.restartExpected, lifecycle.boundary));

    if (replay.length > 0 && incomingScope) {
      if (forceBoundary) {
        const combined = this.takePendingReplayBoundary(incomingScope, replay);
        this.restartExpected = undefined;
        return this.enqueueReplay(combined, true);
      }

      if (pendingMatches || restartMatches) {
        this.stageReplayBoundary(incomingScope, replay);
        return undefined;
      }

      return this.enqueueReplay(replay);
    }

    if (
      lifecycle.boundary &&
      (isResume ||
        scopesMatch(this.pendingReplayBoundary, lifecycle.boundary) ||
        scopesMatch(this.restartExpected, lifecycle.boundary))
    ) {
      if (
        isResume &&
        !scopesMatch(this.pendingReplayBoundary, lifecycle.boundary) &&
        !scopesMatch(this.restartExpected, lifecycle.boundary) &&
        scopesMatch(this.lastActivatedReplay, lifecycle.boundary)
      ) {
        this.lastActivatedReplay = undefined;
        this.restartExpected = undefined;
        return undefined;
      }
      const pending = this.takePendingReplayBoundary(lifecycle.boundary, []);
      this.restartExpected = undefined;
      return this.enqueueReplay(pending, true, lifecycle.boundary);
    }

    return undefined;
  }

  private stageReplayBoundary(
    scope: ReplayScope,
    items: TransportItem[],
  ): void {
    const startsNewBoundary = items.some((item) => replayEventType(item) === 4);
    if (startsNewBoundary || !scopesMatch(this.pendingReplayBoundary, scope)) {
      this.pendingReplayBoundary = { ...scope, bytes: 0, items: [] };
    }
    const pending = this.pendingReplayBoundary;
    if (!pending) return;
    const bytes = items.reduce(
      (total, item) => total + replayItemBytes(item),
      0,
    );
    if (pending.bytes + bytes > REPLAY_BOUNDARY_MAX_BYTES) {
      this.pendingReplayBoundary = undefined;
      this.debug('replay', 'segment-too-large');
      return;
    }
    pending.bytes += bytes;
    pending.items.push(
      ...items.map((item) =>
        withReplayItemInfo(structuredClone(item), replayItemInfo(item)),
      ),
    );
    this.rememberReplayMeta(items);
  }

  private takePendingReplayBoundary(
    scope: ReplayScope,
    incoming: TransportItem[],
  ): TransportItem[] {
    let items = incoming;
    if (scopesMatch(this.pendingReplayBoundary, scope)) {
      items = [...this.pendingReplayBoundary!.items, ...incoming];
    }
    this.pendingReplayBoundary = undefined;
    return items;
  }

  private enqueueCollect(
    items: TransportItem[],
    queue: BoundedConcurrentQueue,
    channel: 'ordinary' | 'traces',
  ): Promise<void> {
    const chunks: TransportItem[][] = [];
    let current: TransportItem[] = [];

    for (const item of items) {
      const candidate = [...current, item];
      let candidateBody: string;
      try {
        candidateBody = JSON.stringify(createCollectBatch(candidate).body);
      } catch {
        this.debug(channel, 'invalid-item');
        continue;
      }

      if (byteLength(candidateBody) <= MAX_COLLECT_BODY_BYTES) {
        current = candidate;
        continue;
      }

      if (current.length > 0) chunks.push(current);
      current = [];

      let singleBody: string;
      try {
        singleBody = JSON.stringify(createCollectBatch([item]).body);
      } catch {
        this.debug(channel, 'invalid-item');
        continue;
      }
      if (byteLength(singleBody) > MAX_COLLECT_BODY_BYTES) {
        this.debug(channel, 'event-too-large');
        continue;
      }
      current = [item];
    }

    if (current.length > 0) chunks.push(current);
    return Promise.all(
      chunks.map((chunk) => this.enqueueCollectChunk(chunk, queue)),
    ).then(() => undefined);
  }

  private enqueueCollectChunk(
    items: TransportItem[],
    queue: BoundedConcurrentQueue,
  ): Promise<void> {
    const batch = createCollectBatch(items);
    const application = requireApplication(items);
    const body = JSON.stringify(batch.body);
    const request: RequestInit = {
      method: 'POST',
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
      headers: {
        'Content-Type': 'application/json',
        [PROTOCOL_HEADERS.apiKey]: this.options.apiKey,
        [PROTOCOL_HEADERS.application]: application,
        [PROTOCOL_HEADERS.batchId]: this.randomId(),
      },
      body,
    };
    return queue.enqueue(
      () =>
        this.sendRequest(this.options.collectUrl, request, byteLength(body)),
      {
        bytes: byteLength(body),
        droppable: items.every(isDroppableOrdinaryItem),
        items: items.length,
      },
    );
  }

  private enqueueReplay(
    items: TransportItem[],
    forceRestart = false,
    fallbackScope?: ReplayScope,
  ): Promise<void> {
    const operations: Promise<void>[] = [];
    const scope = items[0] ? replayScope(items[0]) : fallbackScope;
    if (!scope) {
      this.debug('replay', 'snapshot-required');
      return Promise.resolve();
    }
    const { application, sessionId, userIdentity } = scope;
    this.rememberReplayMeta(items);
    const activeState = this.recordings.values().next().value as
      | RecordingState
      | undefined;
    let state = this.recordings.get(sessionId);
    const stateMatchesIdentity =
      state?.application === application && state.userIdentity === userIdentity;
    const fullSnapshotIndex = items.findIndex(
      (item) => replayEventType(item) === 2,
    );
    const containsOnlyMeta =
      items.length > 0 && items.every((item) => replayEventType(item) === 4);

    if (forceRestart || !stateMatchesIdentity || state?.failed) {
      if (forceRestart || !stateMatchesIdentity) {
        if (activeState && !activeState.failed) {
          operations.push(this.flushReplayAccumulator(activeState));
        }
        // A new Faro session or user identity permanently retires the old
        // recording, even when the new stream has not supplied a safe
        // bootstrap yet. Returning to an earlier identity must never append
        // to its pre-boundary recording.
        this.recordings.clear();
        this.lastActivatedReplay = undefined;
        state = undefined;
      }
      const meta = scopesMatch(this.lastReplayMeta, scope)
        ? this.lastReplayMeta?.item
        : undefined;
      // Faro dispatches rrweb Meta and FullSnapshot as separate transport calls
      // when SDK batching is disabled. rememberReplayMeta already staged this
      // scope, so a pure Meta call is a healthy bootstrap, not data loss.
      if (fullSnapshotIndex < 0 && containsOnlyMeta) {
        return Promise.all(operations).then(() => undefined);
      }
      if (fullSnapshotIndex < 0 || !meta) {
        this.debug('replay', 'snapshot-required');
        return Promise.all(operations).then(() => undefined);
      }
      state = this.activateRecording(sessionId, application, userIdentity);
      const snapshot = items[fullSnapshotIndex]!;
      items = [
        cloneReplayMetaForSnapshot(meta, snapshot),
        ...items.slice(fullSnapshotIndex),
      ];
    }

    if (!state) {
      this.debug('replay', 'snapshot-required');
      return Promise.resolve();
    }

    if (!forceRestart && stateMatchesIdentity)
      this.lastActivatedReplay = undefined;

    operations.push(...this.bufferReplayItems(items, state));
    return Promise.all(operations).then(() => undefined);
  }

  private bufferReplayItems(
    items: TransportItem[],
    state: RecordingState,
  ): Promise<void>[] {
    const operations: Promise<void>[] = [];
    for (const item of items) {
      if (state.failed) break;
      const type = replayEventType(item);
      if (type === undefined) {
        this.quarantineRecording(state);
        this.debug('replay', 'invalid-item');
        break;
      }

      if (type === 4) {
        if (state.accumulator.items.length > 0) {
          if (this.accumulatorAwaitsFullSnapshot(state)) {
            this.quarantineRecording(state);
            this.debug('replay', 'snapshot-required');
            break;
          }
          operations.push(this.flushReplayAccumulator(state));
        }
        this.appendReplayItem(state, item);
        continue;
      }

      if (type === 2) {
        if (!this.accumulatorAwaitsFullSnapshot(state)) {
          this.quarantineRecording(state);
          this.debug('replay', 'snapshot-required');
          break;
        }
        this.appendReplayItem(state, item);
        // Every random-access checkpoint is one self-contained Meta +
        // FullSnapshot segment. Incrementals can never precede its root.
        operations.push(this.flushReplayAccumulator(state));
        continue;
      }

      if (this.accumulatorAwaitsFullSnapshot(state)) {
        this.quarantineRecording(state);
        this.debug('replay', 'snapshot-required');
        break;
      }

      if (this.shouldFlushBeforeReplayItem(state, item)) {
        operations.push(this.flushReplayAccumulator(state));
      }
      this.appendReplayItem(state, item);
      if (this.replayAccumulatorReachedHardTarget(state)) {
        operations.push(this.flushReplayAccumulator(state));
      }
    }
    return operations;
  }

  private appendReplayItem(state: RecordingState, item: TransportItem): void {
    const clone = withReplayItemInfo(
      structuredClone(item),
      replayItemInfo(item),
    );
    state.accumulator.items.push(clone);
    state.accumulator.bytes += replayItemBytes(clone);
    state.accumulator.firstTimestamp ??= replayEventTimestamp(clone);
    if (!state.accumulator.timer) {
      state.accumulator.timer = setTimeout(() => {
        state.accumulator.timer = undefined;
        const operation = this.settle(
          'replay',
          this.flushReplayAccumulator(state),
        );
        this.replayTimerFlush = operation;
        void operation.finally(() => {
          if (this.replayTimerFlush === operation)
            this.replayTimerFlush = undefined;
        });
      }, REPLAY_TARGET_DURATION_MS);
    }
    replayLifecycleFlushers.add(this.flushOnPageLifecycle);
  }

  private accumulatorAwaitsFullSnapshot(state: RecordingState): boolean {
    return (
      state.accumulator.items.length === 1 &&
      replayEventType(state.accumulator.items[0]!) === 4
    );
  }

  private shouldFlushBeforeReplayItem(
    state: RecordingState,
    item: TransportItem,
  ): boolean {
    if (state.accumulator.items.length === 0) return false;
    const maxEvents =
      this.options.replay?.maxSegmentEvents ?? REPLAY_MAX_SEGMENT_EVENTS;
    if (state.accumulator.items.length >= maxEvents) return true;
    if (
      state.accumulator.bytes + replayItemBytes(item) >
      (this.options.replay?.targetSegmentBytes ?? REPLAY_TARGET_BYTES)
    ) {
      return true;
    }
    const timestamp = replayEventTimestamp(item);
    return (
      timestamp !== undefined &&
      state.accumulator.firstTimestamp !== undefined &&
      timestamp - state.accumulator.firstTimestamp >= REPLAY_TARGET_DURATION_MS
    );
  }

  private replayAccumulatorReachedHardTarget(state: RecordingState): boolean {
    return (
      state.accumulator.items.length >=
        (this.options.replay?.maxSegmentEvents ?? REPLAY_MAX_SEGMENT_EVENTS) ||
      state.accumulator.bytes >=
        (this.options.replay?.targetSegmentBytes ?? REPLAY_TARGET_BYTES)
    );
  }

  private flushActiveReplay(pageLifecycle = false): Promise<void> {
    const state = this.recordings.values().next().value as
      | RecordingState
      | undefined;
    return state
      ? this.flushReplayAccumulator(state, pageLifecycle)
      : Promise.resolve();
  }

  private flushReplayAccumulator(
    state: RecordingState,
    pageLifecycle = false,
  ): Promise<void> {
    if (state.accumulator.items.length === 0) return Promise.resolve();
    if (this.accumulatorAwaitsFullSnapshot(state)) {
      this.quarantineRecording(state);
      this.debug('replay', 'snapshot-required');
      return Promise.resolve();
    }

    const items = state.accumulator.items;
    this.resetReplayAccumulator(state);
    const queuedBytes = items.reduce(
      (total, item) => total + replayItemBytes(item),
      0,
    );
    return state.queue
      .enqueue(
        () => {
          if (state.failed) {
            this.debug('replay', 'queue-drop');
            return Promise.resolve();
          }
          return this.sendReplay(items, state, pageLifecycle);
        },
        {
          bytes: queuedBytes,
          // Dropping an accepted Replay segment would create a semantically
          // continuous sequence with missing DOM mutations. Backpressure must
          // quarantine the recording instead.
          droppable: false,
          items: items.length,
        },
      )
      .catch((error) => {
        this.quarantineRecording(state);
        this.debug('replay', 'queue-drop');
        throw error;
      });
  }

  private resetReplayAccumulator(state: RecordingState): void {
    if (state.accumulator.timer) clearTimeout(state.accumulator.timer);
    state.accumulator = { bytes: 0, items: [] };
    if (
      ![...this.recordings.values()].some(
        (recording) => recording.accumulator.items.length > 0,
      )
    ) {
      replayLifecycleFlushers.delete(this.flushOnPageLifecycle);
    }
  }

  private rememberReplayMeta(items: TransportItem[]): void {
    for (const item of items) {
      if (
        replayEventType(item) !== 4 ||
        replayItemBytes(item) > MAX_REPLAY_META_BYTES
      )
        continue;
      const scope = replayScope(item);
      if (!scope) continue;
      this.lastReplayMeta = {
        ...scope,
        item: withReplayItemInfo(structuredClone(item), replayItemInfo(item)),
      };
    }
  }

  private async sendReplay(
    items: TransportItem[],
    state: RecordingState,
    pageLifecycle = false,
  ): Promise<void> {
    try {
      const segments = await buildReplaySegments(items, {
        recordingId: state.recordingId,
        firstSequence: state.nextSequence,
        maxEvents:
          this.options.replay?.maxSegmentEvents ?? REPLAY_MAX_SEGMENT_EVENTS,
        onDrop: (reason) => {
          this.quarantineRecording(state);
          this.debug('replay', reason);
        },
        targetDurationMs: 5_000,
        targetUncompressedBytes:
          this.options.replay?.targetSegmentBytes ?? REPLAY_TARGET_BYTES,
      });
      if (state.failed) return;
      for (const segment of segments) {
        await this.sendReplaySegment(segment, pageLifecycle);
        // Commit only after a confirmed upload. If confirmation is lost, the
        // recording is quarantined below so later events cannot reuse a
        // possibly-published sequence with different bytes.
        state.nextSequence = segment.sequence + 1;
      }
    } catch (error) {
      this.quarantineRecording(state);
      throw error;
    }
  }

  private quarantineRecording(state: RecordingState): void {
    state.failed = true;
    this.resetReplayAccumulator(state);
    // A failed recording may only recover from Meta observed after the
    // failure. Reusing the cached pre-failure Meta with a later FullSnapshot
    // would manufacture a checkpoint that Faro never emitted.
    if (this.recordings.get(state.sessionId) === state)
      this.lastReplayMeta = undefined;
  }

  private activateRecording(
    sessionId: string,
    application: string,
    userIdentity: string,
  ): RecordingState {
    // A browser page has one active Faro session. Session rollover or an
    // explicit Replay boundary retires all older queue references so a
    // long-lived tab cannot grow this map without bound.
    this.recordings.clear();
    const state: RecordingState = {
      accumulator: { bytes: 0, items: [] },
      application,
      failed: false,
      nextSequence: 0,
      queue: this.replayQueue,
      recordingId: this.randomId(),
      sessionId,
      userIdentity,
    };
    this.recordings.set(sessionId, state);
    this.lastActivatedReplay = { application, sessionId, userIdentity };
    return state;
  }

  private async sendReplaySegment(
    segment: ReplaySegment,
    pageLifecycle: boolean,
  ): Promise<void> {
    const request: RequestInit = {
      method: 'POST',
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
      headers: {
        'Content-Encoding': 'gzip',
        'Content-Type': 'application/vnd.weops.rum-replay.v1+json',
        [PROTOCOL_HEADERS.apiKey]: this.options.apiKey,
        [PROTOCOL_HEADERS.sessionId]: segment.sessionId,
        [PROTOCOL_HEADERS.application]: segment.application,
        [PROTOCOL_HEADERS.batchId]: segment.segmentId,
      },
      body: segment.body as BodyInit,
    };
    await this.sendRequest(
      this.options.replayUrl,
      request,
      segment.compressedBytes,
      pageLifecycle,
    );
  }

  private async sendRequest(
    url: string,
    request: RequestInit,
    bytes: number,
    pageLifecycle = false,
  ): Promise<void> {
    const reservation = reserveKeepalive(bytes);
    if (pageLifecycle && !reservation.keepalive) {
      this.debug('replay', 'pagehide-keepalive-unavailable');
    }
    try {
      await requestWithRetry(
        url,
        { ...request, keepalive: reservation.keepalive },
        this.retryOptions,
      );
    } finally {
      reservation.release();
    }
  }

  private settle(
    channel: CoreRumDebugEvent['channel'],
    operation: Promise<void>,
  ): Promise<void> {
    return operation.catch(() => {
      this.debug(channel, 'request-failed');
    });
  }

  private createReplayQueue(): BoundedConcurrentQueue {
    return new BoundedConcurrentQueue(
      {
        maxInFlight: 1,
        maxQueuedBytes: REPLAY_QUEUE_MAX_BYTES,
        maxQueuedItems: Number.MAX_SAFE_INTEGER,
      },
      () => this.debug('replay', 'queue-drop'),
    );
  }

  private debug(
    channel: CoreRumDebugEvent['channel'],
    reason: CoreRumDebugEvent['reason'],
  ): void {
    this.options.debug?.({ channel, reason });
  }
}
