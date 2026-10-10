import { PublicEnumOption } from '@/app/cmdb/types/assetManage';

export function trimPublicEnumText(value: unknown): string {
  return String(value ?? '').trim();
}

export function trimPublicEnumOptions(options: PublicEnumOption[]): PublicEnumOption[] {
  return options.map((option) => ({
    ...option,
    id: trimPublicEnumText(option.id),
    name: trimPublicEnumText(option.name),
  }));
}

export function collectPublicEnumOptionsForSave(options: PublicEnumOption[]): PublicEnumOption[] {
  return trimPublicEnumOptions(options).filter((option) => option.id && option.name);
}
