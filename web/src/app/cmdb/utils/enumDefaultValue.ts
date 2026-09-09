import { EnumList, FullInfoAttrItem, PublicEnumLibraryItem } from '@/app/cmdb/types/assetManage';

export type EnumSelectMode = 'single' | 'multiple';

export type PublicEnumLibraryLoadState = 'unloaded' | 'ready' | 'failed';

export const normalizeDefaultValue = (value: unknown): string[] => {
  const source = Array.isArray(value)
    ? value
    : value === undefined || value === null || value === ''
      ? []
      : [value];

  const seen = new Set<string>();
  return source
    .map((item) => String(item ?? '').trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      seen.add(item);
      return true;
    });
};

export const sanitizeDefaultValue = (
  value: unknown,
  validOptionIds: Iterable<string>,
  selectMode: EnumSelectMode,
): string[] => {
  const optionIdSet = new Set(Array.from(validOptionIds).map((item) => String(item)));
  const validValues = normalizeDefaultValue(value).filter((item) => optionIdSet.has(item));
  return selectMode === 'multiple' ? validValues : validValues.slice(0, 1);
};

export const getEnumOptionIds = (options: EnumList[] = []): string[] => {
  return options
    .map((item) => String(item?.id ?? '').trim())
    .filter(Boolean);
};

export const getAttributeEnumOptionIds = ({
  enumRuleType,
  publicLibraryId,
  publicLibraries,
  enumList,
}: {
  enumRuleType: 'custom' | 'public_library';
  publicLibraryId: string;
  publicLibraries: PublicEnumLibraryItem[];
  enumList: EnumList[];
}): string[] => {
  if (enumRuleType === 'public_library') {
    const currentLibrary = publicLibraries.find((item) => item.library_id === publicLibraryId);
    return getEnumOptionIds(currentLibrary?.options || []);
  }
  return getEnumOptionIds(enumList);
};

export const resolveEnumDefaultValue = ({
  candidate,
  validOptionIds,
  selectMode,
  enumRuleType,
  publicLibraryLoadState,
}: {
  candidate: unknown;
  validOptionIds: Iterable<string>;
  selectMode: EnumSelectMode;
  enumRuleType: 'custom' | 'public_library';
  publicLibraryLoadState: PublicEnumLibraryLoadState;
}): string[] => {
  if (enumRuleType === 'public_library' && publicLibraryLoadState !== 'ready') {
    return normalizeDefaultValue(candidate);
  }
  return sanitizeDefaultValue(candidate, validOptionIds, selectMode);
};

export const canSubmitEnumDefaultValue = ({
  enumRuleType,
  publicLibraryLoadState,
}: {
  enumRuleType: 'custom' | 'public_library';
  publicLibraryLoadState: PublicEnumLibraryLoadState;
}): boolean => {
  if (enumRuleType !== 'public_library') {
    return true;
  }
  return publicLibraryLoadState === 'ready';
};

export const getEnumDefaultValueForForm = (field: FullInfoAttrItem): string | string[] | undefined => {
  const mode = field.enum_select_mode === 'multiple' ? 'multiple' : 'single';
  const enumOptions = Array.isArray(field.option)
    ? field.option.filter(
      (item): item is EnumList => Boolean(item) && typeof item === 'object' && 'id' in item && 'name' in item,
    )
    : [];
  const sanitized = sanitizeDefaultValue(field.default_value, getEnumOptionIds(enumOptions), mode);
  return mode === 'multiple' ? sanitized : sanitized[0];
};
