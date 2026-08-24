import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';
import type { CardListAccentStyle } from '@/app/ops-analysis/utils/cardList';
import type { WidgetConfigFormValues } from './submitConfig';

export type CardListFormState = NonNullable<WidgetConfigFormValues['cardList']>;

export interface CardListPreviewSlots {
  leading?: string;
  leadingStyle?: CardListAccentStyle;
  primary: string;
  secondary?: string;
  badge?: string;
  badgeStyle?: CardListAccentStyle;
  trailingPrimary?: string;
  trailingSecondary?: string;
}

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
): CardListFieldOption[] =>
  fields.map((field) => {
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

export const resolveCardListPreviewSlots = (
  cardList: CardListFormState | undefined,
  options: CardListFieldOption[],
  placeholders: {
    title: string;
    description: string;
    badge: string;
    trailing: string;
    index: string;
  },
): CardListPreviewSlots => {
  const slots: CardListPreviewSlots = {
    primary: resolveCardListFieldLabel(
      cardList?.titleField,
      options,
      placeholders.title,
    ),
  };

  if (trimField(cardList?.descriptionField)) {
    slots.secondary = resolveCardListFieldLabel(
      cardList?.descriptionField,
      options,
      placeholders.description,
    );
  }

  if (cardList?.leading?.type === 'index') {
    slots.leading = placeholders.index;
    if (cardList.leading.style) {
      slots.leadingStyle = cardList.leading.style;
    }
  } else if (cardList?.leading?.type === 'field' && trimField(cardList.leading.field)) {
    slots.leading = resolveCardListFieldLabel(
      cardList.leading.field,
      options,
      placeholders.index,
    );
    if (cardList.leading.style) {
      slots.leadingStyle = cardList.leading.style;
    }
  }

  if (trimField(cardList?.badgeField)) {
    slots.badge = resolveCardListFieldLabel(
      cardList?.badgeField,
      options,
      placeholders.badge,
    );
    if (cardList?.badgeStyle) {
      slots.badgeStyle = cardList.badgeStyle;
    }
  }

  if (trimField(cardList?.trailingPrimaryField)) {
    slots.trailingPrimary = resolveCardListFieldLabel(
      cardList?.trailingPrimaryField,
      options,
      placeholders.trailing,
    );
  }

  if (trimField(cardList?.trailingSecondaryField)) {
    slots.trailingSecondary = resolveCardListFieldLabel(
      cardList?.trailingSecondaryField,
      options,
      placeholders.trailing,
    );
  }

  return slots;
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
