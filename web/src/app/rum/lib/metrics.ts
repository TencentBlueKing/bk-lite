/** Preserve an explicit null. Missing or non-numeric values stay on the old zero. */
export function metricOrZero(value: unknown): number | null {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function countText(value: number | null | undefined): string {
  return value == null ? '—' : String(value);
}

export function sumKnown(values: Array<number | null | undefined>): number | null {
  let total = 0;
  let seen = false;
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      total += value;
      seen = true;
    }
  }
  if (seen) return total;
  return values.length ? null : 0;
}

export function maxKnown(values: Array<number | null | undefined>): number | null {
  let best: number | null = null;
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value) && (best === null || value > best)) {
      best = value;
    }
  }
  return best;
}
