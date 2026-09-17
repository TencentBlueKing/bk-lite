// 未购 CMDB 时目录探测不到 `cmdb.assetChange`，declared 即为 false。
export function canShowIncidentAssetChangeTab(input: {
  declared: boolean;
  instUuids: readonly string[];
}): boolean {
  return input.declared && input.instUuids.length > 0;
}

export function resolveIncidentSelectedAssetUuid(
  instUuids: readonly string[],
  selectedUuid: string,
): string {
  if (instUuids.includes(selectedUuid)) {
    return selectedUuid;
  }
  return instUuids[0] || '';
}
