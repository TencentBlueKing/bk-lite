export interface RelationEdge {
  model_asst_id?: string;
  src_model_id?: string;
  dst_model_id?: string;
  mapping?: string;
  quick_filter?: unknown;
}

export interface QuickFilterSlot {
  modelAsstId: string;
  targetModelId: string;
  labelName: string;
}

export interface RelationFilter {
  model_asst_id: string;
  inst_uuids: string[];
}

const QUICK_FILTER_LIMIT = 2;

export function isQuickFilterOn(value: unknown) {
  return value === true || value === 1 || value === '1' || value === 'true' || value === 'True' || value === '是';
}

/** 下拉出现在「多」的一端，选项是「一」的一端。n:n 出现在目标模型。 */
export function quickFilterEnds(srcModelId: string, dstModelId: string, mapping: string) {
  const src = srcModelId.trim();
  const dst = dstModelId.trim();
  if (!src || !dst) return null;
  if (mapping === 'n:1') return { subjectModelId: src, targetModelId: dst };
  if (mapping === '1:n' || mapping === 'n:n' || mapping === '1:1') {
    return { subjectModelId: dst, targetModelId: src };
  }
  return null;
}

export function quickFilterSlots(
  modelId: string,
  edges: RelationEdge[],
  modelName: (modelId: string) => string,
): QuickFilterSlot[] {
  if (!Array.isArray(edges)) return [];
  const slots: QuickFilterSlot[] = [];
  const seenTargets = new Set<string>();
  for (const edge of edges) {
    if (!isQuickFilterOn(edge.quick_filter)) continue;
    const asstId = String(edge.model_asst_id || '').trim();
    const src = String(edge.src_model_id || '').trim();
    const dst = String(edge.dst_model_id || '').trim();
    if (src !== modelId && dst !== modelId) continue;
    const ends = quickFilterEnds(src, dst, String(edge.mapping || '').trim());
    if (!asstId || !ends || ends.subjectModelId !== modelId || seenTargets.has(ends.targetModelId)) continue;
    seenTargets.add(ends.targetModelId);
    slots.push({
      modelAsstId: asstId,
      targetModelId: ends.targetModelId,
      labelName: modelName(ends.targetModelId) || ends.targetModelId,
    });
  }
  slots.sort((left, right) => left.modelAsstId.localeCompare(right.modelAsstId));
  return slots.slice(0, QUICK_FILTER_LIMIT);
}

export function relationFilterPayload(selected: Record<string, string[]>): RelationFilter[] {
  return Object.entries(selected)
    .filter(([, uuids]) => uuids.length > 0)
    .map(([model_asst_id, inst_uuids]) => ({ model_asst_id, inst_uuids }));
}
