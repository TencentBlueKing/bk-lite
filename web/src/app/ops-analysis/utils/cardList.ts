import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';
import {
  applyValueMapping,
  type ValueMapping,
} from '@/app/ops-analysis/utils/valueMapping';

export const DEFAULT_CARD_LIST_MAX_ITEMS = 100;

/** Card List 专属展示形态：text=文字着色；textWithBackground=文字+浅底；colorBackground=色点 */
export type CardListAccentDisplayType =
  | 'text'
  | 'textWithBackground'
  | 'colorBackground';

export interface CardListAccentStyle {
  displayType?: CardListAccentDisplayType;
  valueMappings?: ValueMapping[];
}

export type CardListLeadingConfig =
  | { type: 'index'; style?: CardListAccentStyle }
  | { type: 'field'; field: string; style?: CardListAccentStyle };

export interface CardListConfig {
  titleField: string;
  descriptionField?: string;
  leading?: CardListLeadingConfig;
  badgeField?: string;
  badgeStyle?: CardListAccentStyle;
  trailingPrimaryField?: string;
  trailingSecondaryField?: string;
  layout?: 'list' | 'grid';
}

export type CardListAccentPresentation =
  | {
      mode: 'plain';
      displayText: string;
    }
  | {
      mode: 'text';
      displayText: string;
      color?: string;
    }
  | {
      mode: 'textWithBackground';
      displayText: string;
      color: string;
      backgroundColor: string;
    }
  | {
      mode: 'colorDot';
      color: string;
      tooltipText: string;
    };

const PERSISTED_ACCENT_DISPLAY_TYPES = new Set<CardListAccentDisplayType>([
  'textWithBackground',
  'colorBackground',
]);

/** 将映射色转成更浅、更透明的背景色（对齐标签浅底样式）。 */
export const softAccentBackground = (
  color: string,
  alpha = 0.16,
): string | undefined => {
  const hex = color.trim().replace(/^#/, '');
  let r: number | undefined;
  let g: number | undefined;
  let b: number | undefined;
  if (/^[0-9a-fA-F]{3}$/.test(hex)) {
    r = parseInt(hex[0] + hex[0], 16);
    g = parseInt(hex[1] + hex[1], 16);
    b = parseInt(hex[2] + hex[2], 16);
  } else if (/^[0-9a-fA-F]{6}$/.test(hex)) {
    r = parseInt(hex.slice(0, 2), 16);
    g = parseInt(hex.slice(2, 4), 16);
    b = parseInt(hex.slice(4, 6), 16);
  } else {
    const rgb = color.match(
      /^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*[\d.]+\s*)?\)$/i,
    );
    if (!rgb) {
      return undefined;
    }
    r = Number(rgb[1]);
    g = Number(rgb[2]);
    b = Number(rgb[3]);
  }
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

export const normalizeCardListAccentStyle = (
  style?: CardListAccentStyle,
): CardListAccentStyle | undefined => {
  if (!style) {
    return undefined;
  }
  const displayType =
    style.displayType && PERSISTED_ACCENT_DISPLAY_TYPES.has(style.displayType)
      ? style.displayType
      : undefined;
  const valueMappings =
    style.valueMappings && style.valueMappings.length > 0
      ? style.valueMappings
      : undefined;
  if (!displayType && !valueMappings) {
    return undefined;
  }
  return {
    ...(displayType ? { displayType } : {}),
    ...(valueMappings ? { valueMappings } : {}),
  };
};

/**
 * Leading / Badge 展示解析：复用表格值映射规则。
 * - text：文字着色
 * - textWithBackground：文字着色 + 同色浅底
 * - colorBackground：色点（需命中颜色；否则回退为文字形态）
 */
export const resolveCardListAccentPresentation = (
  rawText: string,
  style: CardListAccentStyle | undefined,
): CardListAccentPresentation => {
  const mapping = applyValueMapping(rawText, style?.valueMappings);
  const mappedText = mapping?.text?.trim();
  const displayText = mappedText || rawText;
  const color = mapping?.color;

  if (style?.displayType === 'colorBackground' && color) {
    return {
      mode: 'colorDot',
      color,
      tooltipText: displayText,
    };
  }

  if (style?.displayType === 'textWithBackground' && color) {
    const backgroundColor = softAccentBackground(color);
    if (backgroundColor) {
      return {
        mode: 'textWithBackground',
        displayText,
        color,
        backgroundColor,
      };
    }
  }

  if (color) {
    return {
      mode: 'text',
      displayText,
      color,
    };
  }

  return {
    mode: 'plain',
    displayText,
  };
};

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
