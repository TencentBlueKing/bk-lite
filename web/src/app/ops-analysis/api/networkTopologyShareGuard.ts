/**
 * NetworkTopology 分享态编辑 API 防护。
 *
 * 分享态只允许 session detail / metric_values / link_runtime；
 * 其余 WeOps 编辑目录与写操作不得发往正式 `/network_topology/{id}/weops/...`。
 */

export const NETWORK_TOPOLOGY_SHARE_BLOCKED_EDIT_APIS = [
  'getNodeModels',
  'getNodes',
  'getNodeInterfaces',
  'getNodeMetrics',
  'getDimensionValues',
  'saveViewSets',
  'testConnection',
  'testSavedConnection',
  'createNetworkTopology',
  'updateNetworkTopology',
  'deleteNetworkTopology',
] as const;

export type NetworkTopologyShareBlockedEditApi =
  (typeof NETWORK_TOPOLOGY_SHARE_BLOCKED_EDIT_APIS)[number];

export class NetworkTopologyShareEditBlockedError extends Error {
  readonly api: NetworkTopologyShareBlockedEditApi;

  constructor(api: NetworkTopologyShareBlockedEditApi) {
    super(
      `NetworkTopology shareMode 禁止调用编辑接口: ${api}`,
    );
    this.name = 'NetworkTopologyShareEditBlockedError';
    this.api = api;
  }
}

/** 分享上下文（shareMode / session detail / runtime proxy）任一成立即视为分享态。 */
export const isNetworkTopologyShareAccess = ({
  shareMode = false,
  shareDetailOverride = false,
  shareRuntime = false,
}: {
  shareMode?: boolean;
  shareDetailOverride?: boolean;
  shareRuntime?: boolean;
} = {}): boolean =>
  Boolean(shareMode || shareDetailOverride || shareRuntime);

export const rejectNetworkTopologyEditApiInShareMode = (
  shareAccess: boolean,
  api: NetworkTopologyShareBlockedEditApi,
): void => {
  if (!shareAccess) return;
  throw new NetworkTopologyShareEditBlockedError(api);
};
