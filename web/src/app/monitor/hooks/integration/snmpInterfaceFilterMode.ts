export type SnmpInterfaceFilterMode = 'all' | 'exclude' | 'include';

const EXCLUDE_FIELDS = ['iftype_exclude', 'ifdescr_exclude'] as const;
const INCLUDE_FIELDS = ['iftype_include', 'ifdescr_include'] as const;
export const DEFAULT_SNMP_IFTYPE_EXCLUDE = ['24', '53', '131', '135', '136'];

export const getSnmpInterfaceFilterModePatch = (
  changedValues: Record<string, unknown>
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
    patch.iftype_exclude = DEFAULT_SNMP_IFTYPE_EXCLUDE;
  }
  return patch;
};
