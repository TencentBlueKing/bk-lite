import type { FormInstance } from 'antd/es/form';

export const FILTER_MUTEX_PEERS: Record<string, string> = {
  iftype_exclude: 'iftype_include',
  iftype_include: 'iftype_exclude',
  ifdescr_exclude: 'ifdescr_include',
  ifdescr_include: 'ifdescr_exclude',
};

/** 记录同一维度后填写的一侧，仅该侧展示冲突提示 */
export const FILTER_MUTEX_LAST_KEYS: Record<string, string> = {
  iftype_exclude: '_mutex_last_iftype',
  iftype_include: '_mutex_last_iftype',
  ifdescr_exclude: '_mutex_last_ifdescr',
  ifdescr_include: '_mutex_last_ifdescr',
};

const previousValuesByForm = new WeakMap<FormInstance, Record<string, unknown>>();

export const normalizeMutexValues = (value: unknown): string[] => {
  if (value == null || value === '') return [];
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  return String(value)
    .split(/[,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
};

/**
 * 解析单条 ifType：仅接受纯数字，或「数字 - 名称」展示格式（取数字）。
 * 「111-asdf」这类非法输入返回 null。
 */
export const parseIfTypeTag = (raw: unknown): string | null => {
  const text = String(raw ?? '').trim();
  if (!text) return null;
  if (/^\d+$/.test(text)) return text;
  const labeled = text.match(/^(\d+)\s+-\s+.+$/);
  return labeled ? labeled[1] : null;
};

/** 规范化 ifType 多选/tags 值；rejected 为无法识别的原始输入 */
export const normalizeIfTypeTags = (
  value: unknown
): { values: string[]; rejected: string[] } => {
  const list = Array.isArray(value)
    ? value
    : value == null || value === ''
      ? []
      : [value];
  const values: string[] = [];
  const rejected: string[] = [];
  const seen = new Set<string>();
  for (const item of list) {
    const raw = String(item ?? '').trim();
    if (!raw) continue;
    const parsed = parseIfTypeTag(raw);
    if (!parsed) {
      rejected.push(raw);
      continue;
    }
    if (!seen.has(parsed)) {
      seen.add(parsed);
      values.push(parsed);
    }
  }
  return { values, rejected };
};

/**
 * 两侧都有值时，把“后变为非空”的一侧记为后填写侧；冲突解除时清空标记。
 * 先填写的一侧不提示，仅后填写侧右侧红字提示。
 */
export const trackSnmpFilterMutexLastChanged = (
  changedValues: Record<string, unknown>,
  allValues: Record<string, unknown>,
  form: FormInstance
) => {
  const touched = Object.keys(changedValues || {}).filter(
    (field) => field in FILTER_MUTEX_PEERS
  );
  const prev = previousValuesByForm.get(form) || {};
  const patch: Record<string, unknown> = {};

  const pairKeys = new Set<string>();
  touched.forEach((field) => {
    const lastKey = FILTER_MUTEX_LAST_KEYS[field];
    if (lastKey) pairKeys.add(lastKey);
  });

  pairKeys.forEach((lastKey) => {
    const fields = Object.entries(FILTER_MUTEX_LAST_KEYS)
      .filter(([, key]) => key === lastKey)
      .map(([field]) => field);
    if (fields.length !== 2) return;
    const [fieldA, fieldB] = fields;

    const aOcc = normalizeMutexValues(allValues?.[fieldA]).length > 0;
    const bOcc = normalizeMutexValues(allValues?.[fieldB]).length > 0;
    const prevAOcc = normalizeMutexValues(prev[fieldA]).length > 0;
    const prevBOcc = normalizeMutexValues(prev[fieldB]).length > 0;

    if (aOcc && bOcc) {
      const wasConflict = prevAOcc && prevBOcc;
      if (!wasConflict) {
        const newlyA = aOcc && !prevAOcc;
        const newlyB = bOcc && !prevBOcc;
        if (fieldA in (changedValues || {}) && newlyA) {
          patch[lastKey] = fieldA;
        } else if (fieldB in (changedValues || {}) && newlyB) {
          patch[lastKey] = fieldB;
        } else if (fieldA in (changedValues || {}) && aOcc) {
          patch[lastKey] = fieldA;
        } else if (fieldB in (changedValues || {}) && bOcc) {
          patch[lastKey] = fieldB;
        }
      }
      return;
    }

    patch[lastKey] = undefined;
  });

  if (Object.keys(patch).length) {
    form.setFieldsValue(patch);
  }

  previousValuesByForm.set(form, { ...(allValues || {}) });
};

export const getSnmpFilterMutexLastKey = (field: string) =>
  FILTER_MUTEX_LAST_KEYS[field];

/** 保存拦截用：点名互斥的两个字段 */
export const formatSnmpFilterMutexConflict = (
  t: (id: string, defaultMessage?: string, values?: Record<string, string>) => string,
  dimension: 'iftype' | 'ifdescr'
) => {
  const left = dimension === 'iftype' ? 'iftype_exclude' : 'ifdescr_exclude';
  const right = dimension === 'iftype' ? 'iftype_include' : 'ifdescr_include';
  return t('monitor.integrations.filterMutexConflict', '', {
    left: t(`monitor.integrations.filterMutexFields.${left}`),
    right: t(`monitor.integrations.filterMutexFields.${right}`),
  });
};
