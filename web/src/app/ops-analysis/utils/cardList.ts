import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';

export const DEFAULT_CARD_LIST_MAX_ITEMS = 100;

export type CardListLeadingConfig =
  | { type: 'index' }
  | { type: 'field'; field: string };

export interface CardListConfig {
  titleField: string;
  descriptionField?: string;
  leading?: CardListLeadingConfig;
  badgeField?: string;
  trailingPrimaryField?: string;
  trailingSecondaryField?: string;
  layout?: 'list' | 'grid';
}

export interface CardListCard {
  primary: string;
  secondary?: string;
  leading?: string;
  badge?: string;
  trailingPrimary?: string;
  trailingSecondary?: string;
}

export interface CardListParseResult {
  items: CardListCard[];
  total: number;
  truncated: boolean;
  status: 'empty' | 'ready' | 'invalid';
  message?: string;
}

const INVALID_MESSAGE =
  '数据结构不符：卡片列表期望对象数组，或包含 items 数组的记录列表';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

export const formatCardListIndex = (index: number): string =>
  index < 100 ? String(index).padStart(2, '0') : String(index);

export const formatDisplayableScalar = (value: unknown): string | undefined => {
  if (value === null || value === undefined) {
    return undefined;
  }
  if (typeof value === 'string') {
    const text = value.trim();
    return text || undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  return undefined;
};

const extractCardListRows = (rawData: unknown): unknown[] | null => {
  if (Array.isArray(rawData)) {
    return rawData;
  }
  if (isRecord(rawData) && Array.isArray(rawData.items)) {
    return rawData.items;
  }
  return null;
};

export const isEmptyCardListPayload = (rawData: unknown): boolean => {
  if (rawData === null || rawData === undefined) {
    return true;
  }
  if (Array.isArray(rawData)) {
    return rawData.length === 0;
  }
  if (isRecord(rawData) && Array.isArray(rawData.items)) {
    return rawData.items.length === 0;
  }
  return false;
};

const mapRecordToCard = (
  row: Record<string, unknown>,
  config: Pick<
    CardListConfig,
    | 'titleField'
    | 'descriptionField'
    | 'leading'
    | 'badgeField'
    | 'trailingPrimaryField'
    | 'trailingSecondaryField'
  >,
): CardListCard | null => {
  const primary = formatDisplayableScalar(getValueByPath(row, config.titleField));
  if (!primary) {
    return null;
  }

  const card: CardListCard = { primary };
  const secondary = formatDisplayableScalar(
    getValueByPath(row, config.descriptionField),
  );
  if (secondary) {
    card.secondary = secondary;
  }

  if (config.leading?.type === 'field') {
    const leading = formatDisplayableScalar(
      getValueByPath(row, config.leading.field),
    );
    if (leading) {
      card.leading = leading;
    }
  }

  const badge = formatDisplayableScalar(getValueByPath(row, config.badgeField));
  if (badge) {
    card.badge = badge;
  }

  const trailingPrimary = formatDisplayableScalar(
    getValueByPath(row, config.trailingPrimaryField),
  );
  if (trailingPrimary) {
    card.trailingPrimary = trailingPrimary;
  }

  const trailingSecondary = formatDisplayableScalar(
    getValueByPath(row, config.trailingSecondaryField),
  );
  if (trailingSecondary) {
    card.trailingSecondary = trailingSecondary;
  }

  return card;
};

export const parseCardListItems = (
  rawData: unknown,
  config: Pick<
    CardListConfig,
    | 'titleField'
    | 'descriptionField'
    | 'leading'
    | 'badgeField'
    | 'trailingPrimaryField'
    | 'trailingSecondaryField'
  >,
): CardListParseResult => {
  if (isEmptyCardListPayload(rawData)) {
    return {
      items: [],
      total: 0,
      truncated: false,
      status: 'empty',
    };
  }

  const rows = extractCardListRows(rawData);
  if (!rows) {
    return {
      items: [],
      total: 0,
      truncated: false,
      status: 'invalid',
      message: INVALID_MESSAGE,
    };
  }

  const mapped = rows.flatMap((row) => {
    if (!isRecord(row)) {
      return [];
    }
    const card = mapRecordToCard(row, config);
    return card ? [card] : [];
  });

  if (mapped.length === 0) {
    return {
      items: [],
      total: 0,
      truncated: false,
      status: 'invalid',
      message: INVALID_MESSAGE,
    };
  }

  const maxItems = DEFAULT_CARD_LIST_MAX_ITEMS;
  const truncated = mapped.length > maxItems;
  const sliced = truncated ? mapped.slice(0, maxItems) : mapped;
  const withIndex =
    config.leading?.type === 'index'
      ? sliced.map((card, index) => ({
        ...card,
        leading: formatCardListIndex(index + 1),
      }))
      : sliced;

  return {
    items: withIndex,
    total: mapped.length,
    truncated,
    status: 'ready',
  };
};

export const validateCardListPayload = (
  rawData: unknown,
  config: Pick<CardListConfig, 'titleField'>,
): { isValid: boolean; message?: string } => {
  const parsed = parseCardListItems(rawData, config);
  if (parsed.status === 'invalid') {
    return { isValid: false, message: parsed.message || INVALID_MESSAGE };
  }
  return { isValid: true };
};
