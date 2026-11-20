import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';
import { collectSampleFieldKeys } from './chartFieldOptions';
import type { WidgetConfigFormValues } from './submitConfig';

export type CardListFormState = NonNullable<WidgetConfigFormValues['cardList']>;

export interface CardListFieldOption {
  value: string;
  label: string;
  previewLabel: string;
  key: string;
  searchText: string;
}

const trimField = (value?: string) => {
  const trimmed = value?.trim();
  return trimmed || undefined;
};

export const buildCardListFieldOptions = (
  fields: ResponseFieldDefinition[],
  sample?: unknown,
): CardListFieldOption[] => {
  const schemaOptions = fields.map((field) => {
    const key = field.key;
    const title = field.title?.trim() || '';
    const label = title && title !== key ? `${key} (${title})` : key;
    return {
      value: key,
      label,
      previewLabel: title || key,
      key,
      searchText: `${key} ${title}`.toLowerCase(),
    };
  });
  const seen = new Set(schemaOptions.map((option) => option.value));
  const sampleOptions = collectSampleFieldKeys(sample)
    .filter((key) => !seen.has(key))
    .map((key) => ({
      value: key,
      label: key,
      previewLabel: key,
      key,
      searchText: key.toLowerCase(),
    }));
  return [...schemaOptions, ...sampleOptions];
};

export const resolveCardListFieldLabel = (
  fieldKey: string | undefined,
  options: CardListFieldOption[],
  fallback: string,
) => {
  const key = trimField(fieldKey);
  if (!key) {
    return fallback;
  }
  return options.find((item) => item.value === key)?.previewLabel || key;
};

export const resolveCardListOptionalOpenState = (cardList?: CardListFormState) => ({
  leading:
    cardList?.leading?.type === 'index' || cardList?.leading?.type === 'field',
  badge: Boolean(trimField(cardList?.badgeField)),
  trailing: Boolean(
    trimField(cardList?.trailingPrimaryField) ||
      trimField(cardList?.trailingSecondaryField),
  ),
});

export interface CardListSummaryCopy {
  none: string;
  index: string;
  field: string;
  unconfigured: string;
  firstLine: string;
  secondLine: string;
}

export interface CardListOptionalSummaries {
  leading: string;
  badge: string;
  trailing: string;
}

const fieldDisplayName = (
  fieldKey: string | undefined,
  options: CardListFieldOption[],
) => {
  const key = trimField(fieldKey);
  if (!key) return undefined;
  return resolveCardListFieldLabel(key, options, key);
};

/** 折叠头摘要只读当前草稿。显示名优先，不写入配置，也不代表启用。 */
export const resolveCardListOptionalSummaries = (
  cardList: CardListFormState | undefined,
  options: CardListFieldOption[],
  copy: CardListSummaryCopy,
): CardListOptionalSummaries => {
  const leadingType = cardList?.leading?.type;
  let leading = copy.none;
  if (leadingType === 'index') {
    leading = copy.index;
  } else if (leadingType === 'field') {
    const name = fieldDisplayName(cardList?.leading?.field, options);
    leading = `${copy.field} · ${name || copy.unconfigured}`;
  }

  const badgeName = fieldDisplayName(cardList?.badgeField, options);
  const primaryName = fieldDisplayName(cardList?.trailingPrimaryField, options);
  const secondaryName = fieldDisplayName(cardList?.trailingSecondaryField, options);
  let trailing = copy.unconfigured;
  if (primaryName && secondaryName) {
    trailing = `${primaryName} · ${secondaryName}`;
  } else if (primaryName) {
    trailing = `${copy.firstLine} · ${primaryName}`;
  } else if (secondaryName) {
    trailing = `${copy.secondLine} · ${secondaryName}`;
  }

  return {
    leading,
    badge: badgeName || copy.unconfigured,
    trailing,
  };
};

export const findCardListDuplicateFieldUses = (
  cardList: CardListFormState | undefined,
): Record<string, string[]> => {
  const slotByField = new Map<string, string[]>();
  const push = (field: string | undefined, slot: string) => {
    const key = trimField(field);
    if (!key) {
      return;
    }
    const current = slotByField.get(key) || [];
    if (!current.includes(slot)) {
      current.push(slot);
    }
    slotByField.set(key, current);
  };

  push(cardList?.titleField, 'title');
  push(cardList?.descriptionField, 'description');
  if (cardList?.leading?.type === 'field') {
    push(cardList.leading.field, 'leading');
  }
  push(cardList?.badgeField, 'badge');
  push(cardList?.trailingPrimaryField, 'trailing');
  push(cardList?.trailingSecondaryField, 'trailing');

  const duplicates: Record<string, string[]> = {};
  slotByField.forEach((slots, field) => {
    if (slots.length > 1) {
      duplicates[field] = slots;
    }
  });
  return duplicates;
};

export const getCardListDuplicateHintSlots = (
  fieldKey: string | undefined,
  cardList: CardListFormState | undefined,
  currentSlot: string,
) => {
  const key = trimField(fieldKey);
  if (!key) {
    return [];
  }
  return (findCardListDuplicateFieldUses(cardList)[key] || []).filter(
    (slot) => slot !== currentSlot,
  );
};
