export const buildFlowAssetListUrl = (
  objectId?: string | number | null
): string => {
  if (objectId === undefined || objectId === null || objectId === '') {
    return '/monitor/integration/asset';
  }
  return `/monitor/integration/asset?objId=${encodeURIComponent(String(objectId))}`;
};
