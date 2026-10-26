export interface ArchitectureBinding {
  inst_uuid: string;
  model_id: string;
}

export interface ArchitectureNodeStatusItem {
  inst_uuid: string;
  status:
    | 'normal'
    | 'warning'
    | 'critical'
    | 'unmonitored'
    | 'unknown'
    | 'invalid'
    | 'forbidden';
  alert_count: number;
  max_level: string | null;
  monitor_id: string;
  model_id: string;
  inst_name: string;
  /**
   * critical + error is the severe total (the status API stores that total on critical).
   * warning includes warning, info, and any other non-severe level.
   */
  level_counts?: { critical: number; error: number; warning: number };
}

export interface BindingSearchHit {
  inst_uuid: string;
  inst_name: string;
  ip_addr: string;
  model_id: string;
}

export interface ModelOption {
  model_id: string;
  model_name: string;
  /** CMDB model icon reference, when the model list includes one. */
  icn?: string;
}

/** Page size for the binding search list. CMDB fulltext_search_by_model accepts at most 100. */
export const BINDING_SEARCH_PAGE_SIZE = 30;

export interface BindingSearchPage {
  hits: BindingSearchHit[];
  hasMore: boolean;
  total: number;
}

export type BindingSearchMode = 'idle' | 'by-type' | 'by-model-text' | 'fulltext';

export interface SelectionBinding {
  binding: ArchitectureBinding | null;
  followAlert: boolean;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object';

export function readBinding(value: unknown): ArchitectureBinding | null {
  if (!isRecord(value)) return null;
  const instUuid = typeof value.inst_uuid === 'string' ? value.inst_uuid.trim() : '';
  const modelId = typeof value.model_id === 'string' ? value.model_id.trim() : '';
  if (!instUuid || !modelId) return null;
  return { inst_uuid: instUuid, model_id: modelId };
}

export function findSelectionBinding(
  views: unknown,
  selection: { type: string; id: string } | null,
): SelectionBinding | null {
  if (!selection || (selection.type !== 'ITEM' && selection.type !== 'RECTANGLE')) {
    return null;
  }
  const viewList = Array.isArray(views) ? views : [];
  for (const view of viewList) {
    if (!isRecord(view)) continue;
    const collection = selection.type === 'ITEM' ? view.items : view.rectangles;
    const list = Array.isArray(collection) ? collection : [];
    const match = list.find((entry) => isRecord(entry) && entry.id === selection.id);
    if (!isRecord(match)) continue;
    return {
      binding: selection.type === 'ITEM' ? readBinding(match.bkBinding) : null,
      followAlert: selection.type === 'RECTANGLE' && match.bkFollowAlert === true,
    };
  }
  return null;
}

export function normalizeBindingSearchHits(raw: unknown): BindingSearchHit[] {
  const list = Array.isArray(raw) ? raw : [];
  const hits: BindingSearchHit[] = [];
  for (const item of list) {
    if (!isRecord(item)) continue;
    const instUuid = typeof item.inst_uuid === 'string' ? item.inst_uuid.trim() : '';
    const modelId = typeof item.model_id === 'string' ? item.model_id.trim() : '';
    if (!instUuid || !modelId) continue;
    hits.push({
      inst_uuid: instUuid,
      inst_name: typeof item.inst_name === 'string' ? item.inst_name : '',
      ip_addr: typeof item.ip_addr === 'string' ? item.ip_addr : '',
      model_id: modelId,
    });
  }
  return hits;
}

export function bindingSearchMode(keyword: string, modelId: string): BindingSearchMode {
  const text = keyword.trim();
  const model = modelId.trim();
  if (!text && !model) return 'idle';
  if (!text) return 'by-type';
  if (model) return 'by-model-text';
  return 'fulltext';
}

/** One server page; more pages remain while the rows seen so far are below the server total. */
export function bindingPageFromTotal(
  hits: BindingSearchHit[],
  page: number,
  pageSize: number,
  total: number,
): BindingSearchPage {
  return { hits, hasMore: hits.length > 0 && page * pageSize < total, total };
}

/** One page of a result that the server returns in full (keyword search across all models). */
export function sliceBindingPage(
  all: BindingSearchHit[],
  page: number,
  pageSize: number,
): BindingSearchPage {
  const start = (page - 1) * pageSize;
  return {
    hits: all.slice(start, start + pageSize),
    hasMore: start + pageSize < all.length,
    total: all.length,
  };
}

/**
 * Ops-analysis resource_search page.
 * by-type and by-model-text are already one server page.
 * fulltext still arrives as the whole hit list and is sliced here.
 */
export function architectureSearchPage(
  raw: unknown,
  page: number,
  pageSize: number,
): BindingSearchPage {
  const record = isRecord(raw) ? raw : {};
  const hits = normalizeBindingSearchHits(record.hits);
  if (record.mode === 'fulltext') {
    return sliceBindingPage(hits, page, pageSize);
  }
  const total = typeof record.total === 'number' && Number.isFinite(record.total)
    ? record.total
    : hits.length;
  return bindingPageFromTotal(hits, page, pageSize, total);
}

/** Appends a page, skipping rows already listed (offset paging can shift between requests). */
export function appendBindingHits(
  current: BindingSearchHit[],
  next: BindingSearchHit[],
): BindingSearchHit[] {
  const seen = new Set(current.map((hit) => hit.inst_uuid));
  const merged = [...current];
  for (const hit of next) {
    if (seen.has(hit.inst_uuid)) continue;
    seen.add(hit.inst_uuid);
    merged.push(hit);
  }
  return merged;
}

export function bindingModelLabel(models: ModelOption[], modelId: string): string {
  const name = models.find((model) => model.model_id === modelId)?.model_name.trim();
  return name || modelId;
}

export function flattenModelOptions(raw: unknown): ModelOption[] {
  const list = Array.isArray(raw) ? raw : [];
  const options: ModelOption[] = [];
  const visit = (entry: unknown) => {
    if (!isRecord(entry)) return;
    if (typeof entry.model_id === 'string' && entry.model_id) {
      const option: ModelOption = {
        model_id: entry.model_id,
        model_name: typeof entry.model_name === 'string' && entry.model_name
          ? entry.model_name
          : entry.model_id,
      };
      if (typeof entry.icn === 'string' && entry.icn.trim()) {
        option.icn = entry.icn.trim();
      }
      options.push(option);
    }
    if (Array.isArray(entry.list)) entry.list.forEach(visit);
    if (Array.isArray(entry.models)) entry.models.forEach(visit);
  };
  list.forEach(visit);
  return options;
}

export function bindingDisplay(
  status: ArchitectureNodeStatusItem | null | undefined,
  modelName: string,
): { name: string; typeName: string; blocked: 'invalid' | 'forbidden' | 'unknown' | null } {
  if (!status) {
    return { name: '', typeName: '', blocked: 'unknown' };
  }
  if (status.status === 'invalid') {
    return { name: '', typeName: '', blocked: 'invalid' };
  }
  if (status.status === 'forbidden') {
    return { name: '', typeName: '', blocked: 'forbidden' };
  }
  if (!status.inst_name) {
    return { name: '', typeName: '', blocked: 'unknown' };
  }
  return {
    name: status.inst_name,
    typeName: modelName || status.model_id,
    blocked: null,
  };
}
