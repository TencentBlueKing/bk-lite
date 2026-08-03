import axios from 'axios';

export type WidgetQueryErrorCode =
  | 'widget_query_timeout'
  | 'widget_query_transient'
  | 'widget_data_forbidden'
  | 'datasource_missing';

/**
 * Map a Widget data-request failure to a stable report-failed errorCode.
 * Returns undefined for unclassified / non-data-load errors (must not force data_load).
 */
export const classifyWidgetQueryError = (
  error: unknown,
): WidgetQueryErrorCode | undefined => {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    const code = (error.code || '').toUpperCase();
    const message = (error.message || '').toLowerCase();

    if (
      code === 'ECONNABORTED' ||
      code === 'ETIMEDOUT' ||
      status === 408 ||
      status === 504 ||
      message.includes('timeout')
    ) {
      return 'widget_query_timeout';
    }

    if (status === 401 || status === 403) {
      return 'widget_data_forbidden';
    }

    if (status === 404) {
      return 'datasource_missing';
    }

    if (
      status === 429 ||
      status === 502 ||
      status === 503 ||
      code === 'ERR_NETWORK' ||
      code === 'ECONNRESET' ||
      code === 'ECONNREFUSED' ||
      (!error.response &&
        (code.startsWith('ERR_') || message.includes('network')))
    ) {
      return 'widget_query_transient';
    }

    return undefined;
  }

  if (error instanceof Error) {
    const message = error.message.toLowerCase();
    if (message.includes('timeout')) {
      return 'widget_query_timeout';
    }
  }

  return undefined;
};

export const getRequestErrorMessage = (
  error: unknown,
  fallbackMessage: string,
): string => {
  if (axios.isAxiosError(error)) {
    const responseData = error.response?.data;
    if (typeof responseData?.message === 'string' && responseData.message.trim()) {
      return responseData.message.trim();
    }
    if (typeof responseData?.detail === 'string' && responseData.detail.trim()) {
      return responseData.detail.trim();
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }

  if (typeof error === 'string' && error.trim()) {
    return error.trim();
  }

  return fallbackMessage;
};
