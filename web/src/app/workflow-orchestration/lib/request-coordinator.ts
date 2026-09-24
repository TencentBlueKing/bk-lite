export interface RequestTicket {
  id: number;
  visible: boolean;
  signal: AbortSignal;
}

interface BeginOptions {
  visible: boolean;
}

/**
 * 编排中心的“最新请求获胜”协调器。
 *
 * 新请求会取消同一数据域内的旧请求；即使底层未及时中止网络请求，序号校验也会
 * 阻止旧响应覆盖新状态。静默轮询不会打断正在显示 loading 的用户请求。
 */
export function createRequestCoordinator(onVisibleLoadingChange: (loading: boolean) => void) {
  let nextId = 0;
  let latestId = 0;
  let visibleRequestCount = 0;
  const activeRequests = new Set<RequestTicket>();
  const finishedRequests = new WeakSet<RequestTicket>();
  const controllers = new WeakMap<RequestTicket, AbortController>();

  const finish = (ticket: RequestTicket) => {
    if (finishedRequests.has(ticket)) return;
    finishedRequests.add(ticket);
    activeRequests.delete(ticket);
    if (!ticket.visible) return;
    visibleRequestCount = Math.max(0, visibleRequestCount - 1);
    if (visibleRequestCount === 0) onVisibleLoadingChange(false);
  };

  const cancel = (ticket: RequestTicket, invalidateLatest: boolean) => {
    controllers.get(ticket)?.abort();
    if (invalidateLatest && ticket.id === latestId) latestId = ++nextId;
    finish(ticket);
  };

  return {
    begin({ visible }: BeginOptions): RequestTicket | null {
      if (!visible && visibleRequestCount > 0) return null;
      const previousRequests = Array.from(activeRequests);
      const controller = new AbortController();
      const ticket = { id: ++nextId, visible, signal: controller.signal };
      controllers.set(ticket, controller);
      activeRequests.add(ticket);
      latestId = ticket.id;
      if (visible) {
        visibleRequestCount += 1;
        if (visibleRequestCount === 1) onVisibleLoadingChange(true);
      }
      previousRequests.forEach((request) => cancel(request, false));
      return ticket;
    },
    shouldApply(ticket: RequestTicket) {
      return !ticket.signal.aborted && ticket.id === latestId;
    },
    finish,
    cancel(ticket: RequestTicket) {
      cancel(ticket, true);
    },
    invalidate() {
      latestId = ++nextId;
      Array.from(activeRequests).forEach((ticket) => cancel(ticket, false));
    },
  };
}

export type RequestCoordinator = ReturnType<typeof createRequestCoordinator>;
