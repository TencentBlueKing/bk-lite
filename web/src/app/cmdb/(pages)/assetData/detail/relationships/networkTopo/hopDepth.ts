export const NETWORK_TOPO_HOP_OPTIONS = [1, 2, 3] as const;

export type NetworkTopoHop = (typeof NETWORK_TOPO_HOP_OPTIONS)[number];

export const NETWORK_TOPO_DEFAULT_CENTER_HOP: NetworkTopoHop = 1;

export const isNetworkTopoHop = (value: unknown): value is NetworkTopoHop =>
  NETWORK_TOPO_HOP_OPTIONS.includes(value as NetworkTopoHop);

export const parseNetworkTopoHop = (
  value: unknown,
  fallback: NetworkTopoHop = NETWORK_TOPO_DEFAULT_CENTER_HOP
): NetworkTopoHop => {
  const numeric = typeof value === 'string' ? Number(value) : value;
  return isNetworkTopoHop(numeric) ? numeric : fallback;
};
