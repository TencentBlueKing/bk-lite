export const FUNNEL_STEP_MIN = 2;
export const FUNNEL_STEP_MAX = 8;

const STEP_PLACEHOLDERS = ['/', '/checkout'] as const;

export interface FunnelStepValidation {
  ok: boolean;
  steps: string[];
  countError: boolean;
  invalidIndexes: number[];
}

export function blankFunnelStepRows(): string[] {
  return ['', ''];
}

export function funnelStepPlaceholder(index: number): string {
  return STEP_PLACEHOLDERS[index] ?? STEP_PLACEHOLDERS[1];
}

export function funnelStepRowsFromSteps(steps: readonly string[] | null | undefined): string[] {
  const source = Array.isArray(steps) ? steps.map((step) => step ?? '') : [];
  if (source.length >= FUNNEL_STEP_MIN) return source;
  return [...source, ...Array.from({ length: FUNNEL_STEP_MIN - source.length }, () => '')];
}

export function addFunnelStepRow(rows: readonly string[]): string[] {
  if (rows.length >= FUNNEL_STEP_MAX) return [...rows];
  return [...rows, ''];
}

export function removeFunnelStepRow(rows: readonly string[], index: number): string[] {
  if (rows.length <= FUNNEL_STEP_MIN) return [...rows];
  if (!Number.isInteger(index) || index < 0 || index >= rows.length) return [...rows];
  return rows.filter((_, rowIndex) => rowIndex !== index);
}

export function validateFunnelStepRows(rows: readonly string[]): FunnelStepValidation {
  const steps: string[] = [];
  const invalidIndexes: number[] = [];
  rows.forEach((row, index) => {
    const value = row.trim();
    if (!value) return;
    steps.push(value);
    if (!value.startsWith('/')) invalidIndexes.push(index);
  });
  const countError = steps.length < FUNNEL_STEP_MIN || steps.length > FUNNEL_STEP_MAX;
  return {
    ok: !countError && invalidIndexes.length === 0,
    steps,
    countError,
    invalidIndexes,
  };
}
