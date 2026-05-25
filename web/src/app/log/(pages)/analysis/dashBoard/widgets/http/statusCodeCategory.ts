export const HTTP_STATUS_CATEGORY_KEYS = [
  'status_2xx',
  'status_3xx',
  'status_4xx',
  'status_5xx',
  'status_other'
] as const;

export type HttpStatusCategoryKey = (typeof HTTP_STATUS_CATEGORY_KEYS)[number];

export const getHttpStatusCategory = (
  value: unknown
): HttpStatusCategoryKey => {
  const code = Number.parseInt(String(value ?? '').trim(), 10);

  if (!Number.isFinite(code)) {
    return 'status_other';
  }

  if (code >= 200 && code < 300) {
    return 'status_2xx';
  }

  if (code >= 300 && code < 400) {
    return 'status_3xx';
  }

  if (code >= 400 && code < 500) {
    return 'status_4xx';
  }

  if (code >= 500 && code < 600) {
    return 'status_5xx';
  }

  return 'status_other';
};
