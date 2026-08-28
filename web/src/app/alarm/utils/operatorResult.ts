'use client';

import { createElement, type ReactNode } from 'react';
import { message } from 'antd';
import { HandledRequestError } from '@/utils/request';

export interface OperatorItemResult {
  result?: boolean;
  message?: string;
  data?: unknown;
}

export type OperatorResultMap = Record<string, OperatorItemResult>;

/** Collect per-item failure messages from alert/incident operator `data`. */
export const collectOperatorFailureMessages = (
  results: OperatorResultMap | null | undefined
): string[] => {
  if (!results || typeof results !== 'object' || Array.isArray(results)) {
    return [];
  }

  const messages: string[] = [];
  const seen = new Set<string>();

  for (const [id, item] of Object.entries(results)) {
    if (!item || item.result) continue;
    const text = String(item.message || '').trim() || String(id);
    if (seen.has(text)) continue;
    seen.add(text);
    messages.push(text);
  }

  return messages;
};

export const getOperatorResultsFromError = (
  error: unknown
): OperatorResultMap | null => {
  if (!(error instanceof HandledRequestError)) return null;
  const payload = error.payload as { data?: unknown } | undefined;
  const data = payload?.data;
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
  return data as OperatorResultMap;
};

const renderMessageList = (messages: string[]): ReactNode =>
  createElement(
    'div',
    { style: { whiteSpace: 'pre-wrap' } },
    messages.map((text, index) =>
      createElement('div', { key: `${index}-${text}` }, text)
    )
  );

/**
 * Show every failure message from operator `data` (or error payload).
 * Falls back to the provided generic text when no item message exists.
 */
export const showOperatorFailureMessages = (
  results: OperatorResultMap | null | undefined,
  fallback: string,
  error?: unknown
): void => {
  const fromResults = collectOperatorFailureMessages(results);
  const fromError = collectOperatorFailureMessages(
    getOperatorResultsFromError(error)
  );
  const messages = fromResults.length ? fromResults : fromError;

  if (!messages.length) {
    const topLevel =
      error instanceof HandledRequestError
        ? error.message
        : error instanceof Error
          ? error.message
          : '';
    message.error(topLevel || fallback);
    return;
  }

  message.error({
    content: renderMessageList(messages),
    duration: Math.min(4 + messages.length * 2, 12),
  });
};
