export interface CompactKpiValue {
  value: string;
  exactValue?: string;
}

const KPI_SHARED_MIN_FONT_SIZE = 21;
const KPI_SHARED_MAX_FONT_SIZE = 36;
const KPI_BASE_CARD_WIDTH = 160;
const KPI_BASE_FONT_SIZE = 23;
const KPI_CARD_WIDTH_PER_FONT_SIZE = 30;

export function resolveSharedKpiFontSize(cardWidth: number): number {
  const responsiveFontSize =
    KPI_BASE_FONT_SIZE +
    (cardWidth - KPI_BASE_CARD_WIDTH) / KPI_CARD_WIDTH_PER_FONT_SIZE;

  return Math.max(
    KPI_SHARED_MIN_FONT_SIZE,
    Math.min(KPI_SHARED_MAX_FONT_SIZE, responsiveFontSize),
  );
}

export function formatCompactKpiValue(
  value: number | null | undefined,
  locale: string,
): CompactKpiValue {
  if (value == null) {
    return { value: '--' };
  }

  const exactValue = new Intl.NumberFormat(locale).format(value);
  const displayValue = new Intl.NumberFormat(locale, {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);

  return {
    value: displayValue,
    exactValue: displayValue === exactValue ? undefined : exactValue,
  };
}
