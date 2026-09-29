export const NETWORK_COLLECTION_ASSET_MODELS = [
  'switch',
  'router',
  'firewall',
  'loadbalance',
] as const;

export const DEFAULT_NETWORK_ASSET_TAB = NETWORK_COLLECTION_ASSET_MODELS[0];

interface AssetRow {
  inst_uuid?: string;
  model_id?: string;
  ip_addr?: string;
  ip?: string;
  host?: string;
}

export const mergeVisibleNetworkAssetSelection = <T extends AssetRow>(input: {
  previouslySelected: T[];
  visibleInstUuids: Array<string | undefined>;
  checkedRows: T[];
}): T[] => {
  const visible = new Set(
    input.visibleInstUuids.filter((uuid): uuid is string => Boolean(uuid))
  );
  const merged: T[] = [];
  const seen = new Set<string>();

  for (const item of input.previouslySelected) {
    if (!item.inst_uuid || visible.has(item.inst_uuid) || seen.has(item.inst_uuid)) {
      continue;
    }
    seen.add(item.inst_uuid);
    merged.push(item);
  }
  for (const row of input.checkedRows) {
    if (!row.inst_uuid || seen.has(row.inst_uuid)) {
      continue;
    }
    seen.add(row.inst_uuid);
    merged.push(row);
  }
  return merged;
};

export const selectedKeysForNetworkAssetTab = (
  selectedRows: AssetRow[],
  modelId: string
): string[] =>
  selectedRows.flatMap((row) =>
    row.model_id === modelId && row.inst_uuid ? [row.inst_uuid] : []
  );

export const findDuplicateNetworkAssetIp = (
  instances: AssetRow[]
): string | null => {
  const seen = new Set<string>();
  for (const item of instances) {
    const ip = String(item.ip_addr || item.ip || item.host || '').trim();
    if (!ip) {
      continue;
    }
    if (seen.has(ip)) {
      return ip;
    }
    seen.add(ip);
  }
  return null;
};
