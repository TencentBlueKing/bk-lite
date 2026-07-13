export interface WidgetRequestCacheEntry {
  rawData: any;
  baselineData: any;
  errorMessage?: string;
}

const widgetRequestCache = new Map<string, WidgetRequestCacheEntry>();

export const buildWidgetRequestCacheKey = ({
  scopeId,
  requestVersionKey,
  requestSignature,
}: {
  scopeId?: string | number;
  requestVersionKey: string;
  requestSignature: string;
}) => `${scopeId ?? 'dashboard'}:${requestVersionKey}:${requestSignature}`;

export const getCachedWidgetRequest = (
  requestKey: string,
): WidgetRequestCacheEntry | undefined => widgetRequestCache.get(requestKey);

export const setWidgetRequestSuccessCache = (
  requestKey: string,
  entry: WidgetRequestCacheEntry,
) => {
  widgetRequestCache.set(requestKey, entry);
};

export const setWidgetRequestFailureCache = (
  requestKey: string,
  message: string,
) => {
  widgetRequestCache.set(requestKey, {
    rawData: null,
    baselineData: null,
    errorMessage: message,
  });
};
