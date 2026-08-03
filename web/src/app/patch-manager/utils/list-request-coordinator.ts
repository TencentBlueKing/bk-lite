export interface ListRequestTicket {
  id: number;
  visible: boolean;
  signal: AbortSignal;
}

interface BeginListRequestOptions {
  visible: boolean;
}

export interface ListRequestCoordinator {
  begin: (options: BeginListRequestOptions) => ListRequestTicket | null;
  canStart: (options: BeginListRequestOptions) => boolean;
  cancel: (ticket: ListRequestTicket) => void;
  finish: (ticket: ListRequestTicket) => void;
  hasVisibleRequest: () => boolean;
  shouldApply: (ticket: ListRequestTicket) => boolean;
  invalidate: () => void;
}

/**
 * 分离“最新响应所有权”和“可见 loading 生命周期”。
 *
 * 静默轮询可以让旧响应失效，但不能破坏普通请求的 loading 开始/结束配对。
 */
export function createListRequestCoordinator(
  onVisibleLoadingChange: (loading: boolean) => void,
): ListRequestCoordinator {
  let nextId = 0;
  let latestId = 0;
  let visibleRequestCount = 0;
  const finishedRequests = new WeakSet<ListRequestTicket>();
  const activeRequests = new Set<ListRequestTicket>();
  const requestControllers = new WeakMap<ListRequestTicket, AbortController>();

  const finish = (ticket: ListRequestTicket) => {
    if (finishedRequests.has(ticket)) return;
    finishedRequests.add(ticket);
    activeRequests.delete(ticket);
    if (!ticket.visible) return;

    visibleRequestCount = Math.max(0, visibleRequestCount - 1);
    if (visibleRequestCount === 0) onVisibleLoadingChange(false);
  };

  const cancelRequest = (ticket: ListRequestTicket, invalidateLatest: boolean) => {
    requestControllers.get(ticket)?.abort();
    if (invalidateLatest && ticket.id === latestId) latestId = ++nextId;
    finish(ticket);
  };

  return {
    begin({ visible }) {
      if (!visible && visibleRequestCount > 0) return null;
      const previousRequests = Array.from(activeRequests);
      const controller = new AbortController();
      const ticket = { id: ++nextId, visible, signal: controller.signal };
      activeRequests.add(ticket);
      requestControllers.set(ticket, controller);
      latestId = ticket.id;
      if (visible) {
        visibleRequestCount += 1;
        if (visibleRequestCount === 1) onVisibleLoadingChange(true);
      }
      previousRequests.forEach((request) => cancelRequest(request, false));
      return ticket;
    },

    canStart({ visible }) {
      return visible || visibleRequestCount === 0;
    },

    cancel(ticket) {
      cancelRequest(ticket, true);
    },

    finish,

    hasVisibleRequest() {
      return visibleRequestCount > 0;
    },

    shouldApply(ticket) {
      return !ticket.signal.aborted && ticket.id === latestId;
    },

    invalidate() {
      latestId = ++nextId;
      Array.from(activeRequests).forEach((ticket) => cancelRequest(ticket, false));
    },
  };
}
