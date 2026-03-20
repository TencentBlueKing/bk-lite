import type { AttrFieldType, EnumList, UserItem } from '@/app/cmdb/types/assetManage';

interface TagOptionItem {
  key?: string;
  value?: string;
}

interface GroupedSelectOption {
  label: string;
  options: Array<{ label: string; value: string }>;
}

interface SelectOption<T = string | number> {
  label: string;
  value: T;
}

export const getFieldType = (field?: AttrFieldType): string | undefined => {
  if (!field) return undefined;
  return field.attr_id === 'cloud' ? 'cloud' : field.attr_type;
};

export const getEnumOptions = (field?: AttrFieldType): SelectOption[] => {
  if (!field || !Array.isArray(field.option)) {
    return [];
  }
  return (field.option as EnumList[]).map((item) => ({
    label: item.name,
    value: item.id,
  }));
};

export const getTagOptions = (field?: AttrFieldType): GroupedSelectOption[] => {
  if (!field) return [];

  const tagOption = field.option as { options?: TagOptionItem[] } | undefined;
  const source = Array.isArray(tagOption?.options) ? tagOption.options : [];

  const grouped = source.reduce<Record<string, SelectOption<string>[]>>((acc, item) => {
    const key = String(item?.key || '').trim();
    const value = String(item?.value || '').trim();

    if (!key || !value) {
      return acc;
    }

    if (!acc[key]) {
      acc[key] = [];
    }

    acc[key].push({
      label: `${key}:${value}`,
      value: `${key}:${value}`,
    });

    return acc;
  }, {});

  return Object.keys(grouped).map((key) => ({
    label: key,
    options: grouped[key],
  }));
};

export const getTagGroupedValues = (field?: AttrFieldType): Record<string, string[]> => {
  if (!field) return {};

  const tagOption = field.option as { options?: TagOptionItem[] } | undefined;
  const options = Array.isArray(tagOption?.options) ? tagOption.options : [];

  return options.reduce<Record<string, string[]>>((acc, item) => {
    const key = String(item?.key || '').trim();
    const val = String(item?.value || '').trim();

    if (!key || !val) return acc;

    if (!acc[key]) {
      acc[key] = [];
    }

    acc[key].push(val);
    return acc;
  }, {});
};

export const getUserOptions = (userList: UserItem[]): SelectOption<string>[] => {
  return userList.map((user) => ({
    label: `${user.display_name || user.username}(${user.username})`,
    value: user.id,
  }));
};
