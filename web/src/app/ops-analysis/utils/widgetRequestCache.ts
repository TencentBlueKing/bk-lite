export interface WidgetRequestCacheEntry {
  rawData: any;
  baselineData: any;
  dataValidation: { isValid: boolean; message?: string } | null;
}

const widgetRequestCache = new Map<string, WidgetRequestCacheEntry>();

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
    dataValidation: {
      isValid: false,
      message,
    },
  });
};
