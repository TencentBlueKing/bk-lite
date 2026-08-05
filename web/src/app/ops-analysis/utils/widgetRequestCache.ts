const inflightWidgetRequests = new Map<string, Promise<unknown>>();

export const buildWidgetRequestCacheKey = ({
  scopeId,
  requestVersionKey,
  requestSignature,
}: {
  scopeId?: string | number;
  requestVersionKey: string;
  requestSignature: string;
}) => `${scopeId ?? 'dashboard'}:${requestVersionKey}:${requestSignature}`;

export const getOrCreateInflightWidgetRequest = async <T,>(
  requestKey: string,
  createRequest: () => Promise<T>,
): Promise<T> => {
  const existingRequest = inflightWidgetRequests.get(requestKey) as Promise<T> | undefined;
  if (existingRequest) return existingRequest;

  const requestPromise = createRequest().finally(() => {
    inflightWidgetRequests.delete(requestKey);
  });
  inflightWidgetRequests.set(requestKey, requestPromise as Promise<unknown>);
  return requestPromise;
};
