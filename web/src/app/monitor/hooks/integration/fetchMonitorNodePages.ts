export const MONITOR_NODE_PAGE_SIZE = 50;
export const MONITOR_NODE_SEARCH_DELAY_MS = 400;

export interface CachedMonitorNodePage<T> {
  nodes: T[];
  page: number;
  total: number;
}

interface LoadCachedPageArgs<T> {
  keyword: string;
  page: number;
  append: boolean;
  nodeId: (node: T) => string;
  fetchPage: () => Promise<{ count?: number; nodes?: T[] }>;
}

export function createMonitorNodeQueryCache<T>() {
  const pages = new Map<string, CachedMonitorNodePage<T>>();
  const inflight = new Map<string, Promise<CachedMonitorNodePage<T>>>();

  const mergeNodes = (current: T[], batch: T[], nodeId: (node: T) => string) => {
    const seen = new Set<string>();
    return [...current, ...batch].filter((node) => {
      const id = nodeId(node);
      if (!id || seen.has(id)) return false;
      seen.add(id);
      return true;
    });
  };

  return {
    read(keyword: string) {
      return pages.get(keyword);
    },
    load(args: LoadCachedPageArgs<T>) {
      const cached = pages.get(args.keyword);
      if (cached && args.page <= cached.page) {
        return Promise.resolve(cached);
      }
      const flightKey = `${args.keyword}#${args.page}`;
      const pending = inflight.get(flightKey);
      if (pending) return pending;
      const request = args.fetchPage().then((result) => {
        const batch = result.nodes || [];
        const previous = args.append ? pages.get(args.keyword)?.nodes || [] : [];
        const nodes = mergeNodes(previous, batch, args.nodeId);
        const entry = {
          nodes,
          page: args.page,
          total: typeof result.count === 'number' ? result.count : nodes.length,
        };
        pages.set(args.keyword, entry);
        return entry;
      }).finally(() => {
        inflight.delete(flightKey);
      });
      inflight.set(flightKey, request);
      return request;
    },
  };
}

const queryCaches = new Map<string, ReturnType<typeof createMonitorNodeQueryCache<never>>>();

export function monitorNodeQueryCache<T>(scope: string) {
  const existing = queryCaches.get(scope) as ReturnType<typeof createMonitorNodeQueryCache<T>> | undefined;
  if (existing) return existing;
  const created = createMonitorNodeQueryCache<T>();
  queryCaches.set(scope, created as ReturnType<typeof createMonitorNodeQueryCache<never>>);
  return created;
}

export function scheduleMonitorNodeSearch(
  timer: { id?: number },
  delay: number,
  run: () => void,
) {
  if (timer.id) {
    window.clearTimeout(timer.id);
  }
  timer.id = window.setTimeout(run, delay);
}

export function shouldLoadNextMonitorNodePage(
  scrollTop: number,
  clientHeight: number,
  scrollHeight: number,
) {
  return scrollHeight - scrollTop - clientHeight <= 32;
}
