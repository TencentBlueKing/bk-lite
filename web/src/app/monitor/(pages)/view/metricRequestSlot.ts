export const MAX_CONCURRENT_REQUESTS = 4;

export interface WaitForAvailableMetricSlotOptions {
  maxConcurrent?: number;
  intervalMs?: number;
  sleep?: (ms: number) => Promise<void>;
}

export type MetricRequestOutcome = 'ok' | 'failed' | 'aborted' | 'superseded';

export interface RunMetricRangeQueryOptions<T> {
  slots: Map<number, AbortController>;
  metricId: number;
  controller: AbortController;
  postQuery: () => Promise<T>;
  handleResponse?: (response: T) => void | Promise<void>;
  onSettled?: (released: boolean) => void;
}

function errorName(error: unknown): string {
  if (error && typeof error === 'object' && 'name' in error) {
    const name = (error as { name: unknown }).name;
    return typeof name === 'string' ? name : '';
  }
  return '';
}

export function occupyMetricRequestSlot(
  slots: Map<number, AbortController>,
  metricId: number,
  controller: AbortController
): void {
  slots.set(metricId, controller);
}

export function releaseMetricRequestSlot(
  slots: Map<number, AbortController>,
  metricId: number,
  controller: AbortController
): boolean {
  if (slots.get(metricId) !== controller) {
    return false;
  }
  slots.delete(metricId);
  return true;
}

export async function waitForAvailableMetricSlot(
  slots: Map<number, AbortController>,
  isCurrentGeneration: () => boolean,
  options?: WaitForAvailableMetricSlotOptions
): Promise<boolean> {
  const maxConcurrent = options?.maxConcurrent ?? MAX_CONCURRENT_REQUESTS;
  const intervalMs = options?.intervalMs ?? 30;
  const sleep =
    options?.sleep ??
    ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));

  while (slots.size >= maxConcurrent) {
    await sleep(intervalMs);
    if (!isCurrentGeneration()) {
      return false;
    }
  }
  return isCurrentGeneration();
}

export async function runMetricRangeQuery<T>({
  slots,
  metricId,
  controller,
  postQuery,
  handleResponse,
  onSettled,
}: RunMetricRangeQueryOptions<T>): Promise<MetricRequestOutcome> {
  occupyMetricRequestSlot(slots, metricId, controller);
  let outcome: MetricRequestOutcome = 'failed';
  try {
    const response = await postQuery();
    if (slots.get(metricId) !== controller) {
      outcome = 'superseded';
      return outcome;
    }
    await handleResponse?.(response);
    outcome = 'ok';
    return outcome;
  } catch (error: unknown) {
    const name = errorName(error);
    if (name === 'AbortError' || name === 'CancelledError') {
      outcome = 'aborted';
      return outcome;
    }
    outcome = 'failed';
    return outcome;
  } finally {
    const released = releaseMetricRequestSlot(slots, metricId, controller);
    onSettled?.(released);
  }
}
