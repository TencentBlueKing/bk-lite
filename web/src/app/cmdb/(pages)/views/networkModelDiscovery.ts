/**
 * Network-capable model ids = destinations of interface --belong--> <model>,
 * matching backend topology_theme.is_network_device_model and NetworkTopo prefetch.
 */

export interface ModelAssociationLike {
  asst_id?: string;
  src_model_id?: string;
  dst_model_id?: string;
}

export const networkModelIdsFromInterfaceAssociations = (
  associations: ModelAssociationLike[] | null | undefined
): string[] => {
  const seen = new Set<string>();
  const ids: string[] = [];
  for (const assoc of Array.isArray(associations) ? associations : []) {
    if (
      assoc?.asst_id === 'belong'
      && assoc.src_model_id === 'interface'
      && typeof assoc.dst_model_id === 'string'
      && assoc.dst_model_id
      && !seen.has(assoc.dst_model_id)
    ) {
      seen.add(assoc.dst_model_id);
      ids.push(assoc.dst_model_id);
    }
  }
  return ids;
};

/** Keep only network models that exist in the current org model list (stable order). */
export const filterNetworkModelIdsByCatalog = (
  catalogModelIds: string[],
  networkModelIds: string[]
): string[] => {
  const allowed = new Set(networkModelIds);
  return catalogModelIds.filter((id) => allowed.has(id));
};
