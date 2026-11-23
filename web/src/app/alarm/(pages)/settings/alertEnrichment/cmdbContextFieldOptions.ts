export const EXPECTED_CONTEXT_MODELS = ['application', 'system'] as const;

export interface CmdbContextField {
  source: string;
  attr_id?: string;
  attr_name?: string;
}

export interface CmdbContextFieldGroup {
  model_id: string;
  model_name?: string;
  fields?: CmdbContextField[];
}

export interface ContextFieldOption {
  value: string;
  label: string;
}

export interface ContextFieldOptionGroup {
  label: string;
  options: ContextFieldOption[];
}

function fieldAttrId(field: CmdbContextField) {
  if (field.attr_id) return field.attr_id;
  const source = String(field.source || '');
  const dot = source.lastIndexOf('.');
  return dot >= 0 ? source.slice(dot + 1) : source;
}

function sortContextFields(fields: CmdbContextField[]) {
  return [...fields].sort((left, right) => {
    const leftName = fieldAttrId(left) === 'inst_name';
    const rightName = fieldAttrId(right) === 'inst_name';
    if (leftName === rightName) return 0;
    return leftName ? -1 : 1;
  });
}

export function mapCmdbContextFieldGroups(
  groups: CmdbContextFieldGroup[] | undefined
): ContextFieldOptionGroup[] {
  return (groups || [])
    .filter((group) => group?.model_id)
    .map((group) => ({
      label: group.model_name || group.model_id,
      options: sortContextFields(group.fields || []).map((field) => ({
        value: field.source,
        label: field.attr_name
          ? `${field.attr_name} (${field.source})`
          : field.source,
      })),
    }));
}

export function contextFieldCatalogIncomplete(
  groups: CmdbContextFieldGroup[] | undefined
) {
  const ids = new Set((groups || []).map((group) => group.model_id));
  return EXPECTED_CONTEXT_MODELS.some((modelId) => !ids.has(modelId));
}

export function flattenContextFieldOptions(groups: ContextFieldOptionGroup[]) {
  const items: ContextFieldOption[] = [];
  for (const group of groups || []) {
    for (const item of group.options || []) {
      if (!item?.value) continue;
      items.push({ value: item.value, label: String(item.label || item.value) });
    }
  }
  return items;
}

export function displayProjectionSource(
  source: string,
  groups: ContextFieldOptionGroup[]
) {
  const key = String(source || '');
  if (!key) return key;
  const hit = flattenContextFieldOptions(groups).find((item) => item.value === key);
  return hit?.label || key;
}

export function resolveProjectionSource(
  text: string,
  groups: ContextFieldOptionGroup[]
) {
  const raw = String(text || '');
  const trimmed = raw.trim();
  if (!trimmed) return raw;
  const items = flattenContextFieldOptions(groups);
  const byValue = items.find((item) => item.value === trimmed);
  if (byValue) return byValue.value;
  const byLabel = items.find((item) => item.label === trimmed);
  if (byLabel) return byLabel.value;
  return raw;
}

export function matchProjectionSourceFilter(
  input: string,
  option: { value?: string; label?: unknown; options?: ContextFieldOption[] } | undefined,
  groups: ContextFieldOptionGroup[]
) {
  const fieldItems = flattenContextFieldOptions(groups);
  const exactSelected = fieldItems.some(
    (item) => item.value === input || item.label === input
  );
  if (exactSelected) return true;
  const query = String(input || '').trim().toLowerCase();
  if (!query) return true;
  const value = String(option?.value ?? '').toLowerCase();
  const label = String(option?.label ?? '').toLowerCase();
  if (value.includes(query) || label.includes(query)) return true;
  const children = option?.options;
  if (Array.isArray(children)) {
    return children.some(
      (child) =>
        String(child.value || '').toLowerCase().includes(query) ||
        String(child.label || '').toLowerCase().includes(query)
    );
  }
  const parent = groups.find((group) =>
    group.options.some((item) => item.value === option?.value)
  );
  return Boolean(parent && parent.label.toLowerCase().includes(query));
}

export function contextFieldOptionsKey(groups: ContextFieldOptionGroup[]) {
  return groups
    .map((group) => `${group.label}:${group.options.length}`)
    .join('|');
}
