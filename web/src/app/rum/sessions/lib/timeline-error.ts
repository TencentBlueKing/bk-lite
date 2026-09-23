import { displayRoute } from '@/app/rum/lib/format';

/** Privacy-hashed exception text from the RUM collector (`message:<hex>`). */
export function isProtectedRumMessage(value: string): boolean {
  return /^message:[0-9a-f]+$/i.test(value.trim());
}

export function timelineErrorFields(raw: Record<string, unknown> | undefined): {
  message: string;
  errorType: string;
  traceId: string;
  fingerprint: string;
  route: string;
} {
  return {
    message: String(raw?.message || raw?.errorMessage || '').trim(),
    errorType: String(raw?.errorType || '').trim(),
    traceId: String(raw?.traceId || '').trim(),
    fingerprint: String(raw?.fingerprint || '').trim(),
    route: displayRoute(String(raw?.route || '').trim()),
  };
}

export interface TimelineErrorPresentation {
  title: string;
  /** Secondary line; omit when empty — never render an empty shell. */
  hint: string | null;
  protectedMessage: boolean;
  traceId: string | null;
  fingerprint: string | null;
  route: string | null;
}

/**
 * Session-timeline error row. Hashed free-text bodies are not shown as titles;
 * keep type / route / fingerprint so the row is still actionable.
 */
export function presentTimelineError(
  raw: Record<string, unknown> | undefined,
  fallbackTitle = '异常错误',
): TimelineErrorPresentation {
  const { message, errorType, traceId, fingerprint, route } = timelineErrorFields(raw);
  const protectedMessage = isProtectedRumMessage(message);
  if (protectedMessage) {
    return {
      title: errorType || fallbackTitle,
      hint: route || null,
      protectedMessage: true,
      traceId: traceId || null,
      fingerprint: fingerprint || null,
      route: route || null,
    };
  }
  const title = message || errorType || fallbackTitle;
  const typeHint =
    errorType && errorType !== title && !title.startsWith(`${errorType}:`)
      ? errorType
      : null;
  const hint = typeHint || route || null;
  return {
    title,
    hint,
    protectedMessage: false,
    traceId: traceId || null,
    fingerprint: fingerprint || null,
    route: route || null,
  };
}
