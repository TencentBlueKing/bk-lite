import { message } from 'antd';
import type { ReactNode } from 'react';

/** Align with antdConfig defaults; apply once so interceptor toasts honor maxCount. */
let messageConfigured = false;

const ensureMessageConfig = () => {
  if (messageConfigured) return;
  message.config({
    top: 80,
    maxCount: 2,
    duration: 3,
  });
  messageConfigured = true;
};

const recentPlainErrors = new Map<string, number>();
export const REQUEST_ERROR_TOAST_DEDUPE_WINDOW_MS = 3000;

/**
 * Decide whether a dedupe key should emit now. Empty keys always emit (rich content).
 * Exported for unit verification without mounting antd.
 */
export const shouldEmitDedupedErrorKey = (
  dedupeKey: string,
  now = Date.now(),
  store: Map<string, number> = recentPlainErrors,
  windowMs = REQUEST_ERROR_TOAST_DEDUPE_WINDOW_MS,
): boolean => {
  if (!dedupeKey) return true;
  const lastShownAt = store.get(dedupeKey);
  if (lastShownAt != null && now - lastShownAt < windowMs) {
    return false;
  }
  store.set(dedupeKey, now);
  return true;
};

/**
 * Show an error toast, collapsing identical plain-text messages within a short window.
 * Prevents dashboard/search parallel 400s from stacking dozens of the same popup.
 */
export const showRequestErrorToast = (
  content: ReactNode,
  options?: { duration?: number; dedupeKey?: string },
) => {
  ensureMessageConfig();

  const dedupeKey =
    options?.dedupeKey ??
    (typeof content === 'string' ? content.trim() : '');

  if (!shouldEmitDedupedErrorKey(dedupeKey)) {
    return false;
  }

  if (typeof content === 'string') {
    message.error(content);
  } else {
    message.error({
      content,
      duration: options?.duration ?? 8,
    });
  }
  return true;
};

/** Test seam: clear dedupe state between assertions. */
export const resetRequestErrorToastDedupe = () => {
  recentPlainErrors.clear();
};
