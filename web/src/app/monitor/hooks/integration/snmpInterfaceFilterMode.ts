export type SnmpInterfaceFilterMode = 'all' | 'exclude' | 'include';

const EXCLUDE_FIELDS = ['iftype_exclude', 'ifdescr_exclude'] as const;
const INCLUDE_FIELDS = ['iftype_include', 'ifdescr_include'] as const;
export const DEFAULT_SNMP_IFTYPE_EXCLUDE = ['24', '53', '131', '135', '136'];

const hasFilterValues = (value: unknown): boolean => {
  if (value == null || value === '') return false;
  if (Array.isArray(value)) {
    return value.some((item) => String(item ?? '').trim());
  }
  return String(value)
    .split(/[,，]/)
    .some((item) => item.trim());
};

/**
 * 从已下发的黑白名单字段反推采集策略。
 * include 优先于 exclude；两侧皆空视为全部采集。
 */
export const resolveSnmpInterfaceFilterMode = (values: {
  iftype_include?: unknown;
  iftype_exclude?: unknown;
  ifdescr_include?: unknown;
  ifdescr_exclude?: unknown;
}): SnmpInterfaceFilterMode => {
  const hasInclude =
    hasFilterValues(values.iftype_include) || hasFilterValues(values.ifdescr_include);
  if (hasInclude) return 'include';
  const hasExclude =
    hasFilterValues(values.iftype_exclude) || hasFilterValues(values.ifdescr_exclude);
  if (hasExclude) return 'exclude';
  return 'all';
};

export const getSnmpInterfaceFilterModePatch = (
  changedValues: Record<string, unknown>,
  defaultIfTypeExclude: unknown = DEFAULT_SNMP_IFTYPE_EXCLUDE
): Record<string, unknown> => {
  const mode = changedValues.interface_filter_mode as SnmpInterfaceFilterMode | undefined;
  if (!mode) return {};

  const fieldsToClear =
    mode === 'all'
      ? [...EXCLUDE_FIELDS, ...INCLUDE_FIELDS]
      : mode === 'exclude'
        ? INCLUDE_FIELDS
        : EXCLUDE_FIELDS;

  const patch = Object.fromEntries(
    fieldsToClear.map((field) => [field, field.startsWith('iftype') ? [] : ''])
  );
  // 切回“排除部分”时恢复产品默认的虚拟接口排除，避免策略名称与实际规则不一致。
  if (mode === 'exclude') {
    patch.iftype_exclude = Array.isArray(defaultIfTypeExclude)
      ? defaultIfTypeExclude.map((value) => String(value).trim()).filter(Boolean)
      : DEFAULT_SNMP_IFTYPE_EXCLUDE;
  }
  return patch;
};
