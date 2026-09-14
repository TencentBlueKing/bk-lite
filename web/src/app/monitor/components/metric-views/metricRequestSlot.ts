export const MAX_CONCURRENT_METRIC_REQUESTS = 4;

export function occupyMetricRequestSlot(
  slots: Map<number, AbortController>,
  metricId: number,
  controller: AbortController,
): void {
  slots.set(metricId, controller);
}

export function isCurrentMetricRequestSlot(
  slots: Map<number, AbortController>,
  metricId: number,
  controller: AbortController,
): boolean {
  return slots.get(metricId) === controller;
}

export function releaseMetricRequestSlotIfCurrent(
  slots: Map<number, AbortController>,
  metricId: number,
  controller: AbortController,
): boolean {
  if (!isCurrentMetricRequestSlot(slots, metricId, controller)) {
    return false;
  }
  slots.delete(metricId);
  return true;
}

export function canEnterMetricRequestSlot(
  slots: Map<number, AbortController>,
  limit = MAX_CONCURRENT_METRIC_REQUESTS,
): boolean {
  return slots.size < limit;
}

interface ExecuteMetricViewRequestInput<T> {
  slots: Map<number, AbortController>;
  metricId: number;
  controller: AbortController;
  post: () => Promise<T>;
  handleResponse?: (response: T) => void | Promise<void>;
  onCancelled?: () => void;
  onCurrentSettled?: () => void;
}

function errorName(error: unknown): string {
  if (error && typeof error === 'object' && 'name' in error) {
    return String((error as { name: unknown }).name);
  }
  return '';
}

export async function executeMetricViewRequest<T>(
  input: ExecuteMetricViewRequestInput<T>,
): Promise<void> {
  occupyMetricRequestSlot(input.slots, input.metricId, input.controller);
  try {
    const response = await input.post();
    if (!isCurrentMetricRequestSlot(input.slots, input.metricId, input.controller)) {
      return;
    }
    await input.handleResponse?.(response);
  } catch (error: unknown) {
    if (errorName(error) === 'CancelledError') {
      input.onCancelled?.();
    }
  } finally {
    if (releaseMetricRequestSlotIfCurrent(input.slots, input.metricId, input.controller)) {
      input.onCurrentSettled?.();
    }
  }
}
