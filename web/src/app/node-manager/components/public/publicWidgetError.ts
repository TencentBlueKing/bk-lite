import { HandledRequestError } from '@/utils/request';

export function publicWidgetErrorMessage(
  error: unknown,
  t: (id: string) => string,
  notFoundKey: string,
): string {
  const status =
    error instanceof HandledRequestError ? error.status : undefined;
  if (status === 403) return t('common.noAuth');
  if (status === 404) return t(notFoundKey);
  return t('common.loadFailed');
}
